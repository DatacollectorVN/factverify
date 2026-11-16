"""Render the ledger's AFC scores as one standalone HTML page.

Reads ``afc_scores`` joined to ``experiments`` (read-only) and writes a page
with a ``p_forget`` vs ``p_retain`` scatter, coloured and shaped by verdict, a
zoom on the "not forgotten" runs, and the same data as a table. Needs only the
standard library; the page loads nothing external.

    uv run python scripts/afc_scatter_html.py
    uv run python scripts/afc_scatter_html.py --job-prefix phase2- --output reports/phase2-afc-scatter.html
"""

from __future__ import annotations

import argparse
import html as _html
import math
import re
import sqlite3
import sys
from pathlib import Path
from typing import Any, Callable

Row = dict[str, Any]
Box = tuple[float, float, float, float]
Scale = Callable[[float], float]

DEFAULT_LEDGER = Path(".factverify_internal/factverify.sqlite")
DEFAULT_OUTPUT = Path("reports/afc-scatter.html")

#: Stored verdict -> (key, display label). Order is the legend order.
VERDICTS = {
    "certified": ("certified", "Certified"),
    "not certified: not forgotten": ("not_forgotten", "Not forgotten"),
    "not certified: collateral damage": ("collateral", "Collateral damage"),
    "not certified: both failed": ("both", "Both failed"),
}
#: (p_forget passes, p_retain passes) -> the verdict key those results imply.
EXPECTED_KEY = {
    (True, True): "certified",
    (False, True): "not_forgotten",
    (True, False): "collateral",
    (False, False): "both",
}
METHODS = {"ga": "GA", "graddiff": "GradDiff", "npo": "NPO", "rmu": "RMU"}

#: The x axis is compressed left of this log10(p), so the area around alpha stays readable.
X_BREAK = -2.0
#: Share of the plot width used left of the break.
X_BREAK_SHARE = 0.55

WIDTH, HEIGHT = 900, 560
LEFT, RIGHT, TOP, BOTTOM = 78, 18, 14, 54
PLOT_W, PLOT_H = WIDTH - LEFT - RIGHT, HEIGHT - TOP - BOTTOM
PLOT_BOTTOM = TOP + PLOT_H
PLOT_RIGHT = WIDTH - RIGHT
LABEL_BOUNDS: Box = (LEFT + 2, TOP + 2, PLOT_RIGHT - 2, PLOT_BOTTOM - 2)
CHAR_W, LABEL_H = 6.5, 14
LABEL_OFFSETS = (0, -17, 17, -34, 34, -51, 51, -68, 68, -85, 85)

DARK_TOKENS = (
    "--surface:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;--muted:#a09f97;--grid:#33322f;"
    "--region:#1d3a2e;--v-not_forgotten:#3987e5;--v-collateral:#d95926;--v-certified:#199e70"
)
STYLE = f"""<style>
:root{{--surface:#fcfcfb;--ink:#0b0b0b;--ink2:#52514e;--muted:#6f6e69;--grid:#e6e5e0;--region:#e3f4ec;
  --v-not_forgotten:#2a78d6;--v-collateral:#eb6834;--v-certified:#1baf7a}}
@media (prefers-color-scheme:dark){{:root:not([data-theme="light"]){{{DARK_TOKENS}}}}}
:root[data-theme="dark"]{{{DARK_TOKENS}}}
*{{box-sizing:border-box}}
body{{margin:0;padding:24px 16px;background:var(--surface);color:var(--ink);
  font-family:system-ui,-apple-system,"Segoe UI",sans-serif}}
main{{max-width:940px;margin:0 auto}}
h1{{font-size:21px;margin:0 0 6px}}
h2{{font-size:15px;font-weight:600;margin:32px 0 2px}}
p{{margin:0 0 10px;font-size:13px;line-height:1.5;color:var(--ink2)}}
.legend{{display:flex;flex-wrap:wrap;gap:6px 18px;font-size:12.5px;color:var(--ink2);margin:10px 0 6px}}
.legend span{{display:inline-flex;align-items:center;gap:6px}}
svg.chart{{display:block;width:100%;height:auto}}
svg.icon{{width:18px;height:18px;flex:none}}
td svg.icon{{display:inline-block;vertical-align:-4px;margin-right:5px}}
.scroll{{overflow-x:auto}}
table{{border-collapse:collapse;font-size:12.5px;width:100%}}
th{{text-align:left;font-weight:600;color:var(--ink2);border-bottom:1px solid var(--grid);padding:5px 8px;white-space:nowrap}}
td{{padding:5px 8px;border-bottom:1px solid var(--grid);white-space:nowrap}}
.num{{text-align:right;font-variant-numeric:tabular-nums}}
</style>"""


class ReportError(Exception):
    """The ledger's rows cannot be drawn as one chart."""


def esc(value: Any) -> str:
    return _html.escape(str(value))


# --- data ---------------------------------------------------------------------------------


def load_rows(ledger: Path, job_prefix: str) -> list[Row]:
    """Return every AFC row whose job name starts with *job_prefix*, oldest first."""
    con = sqlite3.connect(f"file:{ledger}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute(
            """SELECT e.job_name, a.epoch, a.alpha, a.kappa, a.p_forget, a.p_retain, a.p_afc,
                      a.lowest_retention_bound, a.weakest_family, a.target_min_drop, a.verdict
               FROM afc_scores a JOIN experiments e USING (experiment_id)
               WHERE e.job_name LIKE ? ORDER BY e.created_at""",
            (job_prefix + "%",),
        ).fetchall()
    finally:
        con.close()
    return [dict(row) for row in rows]


def short_name(job_name: str) -> str:
    """``phase2-pythia410m-alias-rmu-L7-c90`` -> ``RMU L7 c90``."""
    name = re.sub(r"^[a-z0-9]+-pythia410m-alias-", "", job_name)
    head, _, rest = name.partition("-")
    rest = re.sub(r"(?<!\de)-", " ", rest)  # keep the minus sign in values like 5e-5
    return f"{METHODS.get(head, head)} {rest}".strip()


def classify(rows: list[Row]) -> tuple[list[Row], list[Row], float]:
    """Split rows into plotted and not plotted, and return the shared alpha."""
    points: list[Row] = []
    excluded: list[Row] = []
    for row in rows:
        row["name"] = short_name(row["job_name"])
        if row["p_forget"] is None or row["p_retain"] is None or row["verdict"] not in VERDICTS:
            excluded.append(row)
            continue
        row["key"], row["label"] = VERDICTS[row["verdict"]]
        points.append(row)
    if not points:
        raise ReportError("no rows have both p_forget and p_retain")

    alphas = sorted({row["alpha"] for row in points})
    if len(alphas) != 1:
        raise ReportError(f"expected one alpha across plotted rows, found {alphas}")
    alpha = alphas[0]

    mismatch = [
        row["job_name"]
        for row in points
        if EXPECTED_KEY[(row["p_forget"] <= alpha, row["p_retain"] <= alpha)] != row["key"]
    ]
    if mismatch:
        raise ReportError(f"stored verdict disagrees with p-values and alpha: {mismatch}")
    return points, excluded, alpha


# --- drawing primitives -------------------------------------------------------------------


def format_p(value: float | None) -> str:
    if value is None:
        return "–"
    if value != 0 and abs(value) < 1e-3:
        return f"{value:.2g}"
    return f"{value:.3f}"


def mark(cx: float, cy: float, key: str, r: float = 6.5) -> str:
    """One point. Each verdict has its own shape, so colour is never the only cue."""
    ring = 'stroke="var(--surface)" stroke-width="2"'
    if key == "certified":
        return f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r}" fill="var(--v-certified)" {ring}/>'
    if key == "not_forgotten":
        s = r * 1.75
        return (
            f'<rect x="{cx - s / 2:.1f}" y="{cy - s / 2:.1f}" width="{s:.1f}" height="{s:.1f}" '
            f'rx="2" fill="var(--v-not_forgotten)" {ring}/>'
        )
    if key == "collateral":
        q = r * 1.25
        return (
            f'<path d="M{cx:.1f} {cy - q:.1f}L{cx + q:.1f} {cy + q * 0.8:.1f}'
            f'L{cx - q:.1f} {cy + q * 0.8:.1f}Z" fill="var(--v-collateral)" {ring} stroke-linejoin="round"/>'
        )

    def diamond(q: float, fill: str, extra: str = "") -> str:
        return (
            f'<path d="M{cx:.1f} {cy - q:.1f}L{cx + q:.1f} {cy:.1f}L{cx:.1f} {cy + q:.1f}'
            f'L{cx - q:.1f} {cy:.1f}Z" fill="{fill}" {extra}/>'
        )

    # Both failed: the two failure colours combined.
    return diamond(r * 1.45, "var(--v-not_forgotten)", ring) + diamond(r * 0.8, "var(--v-collateral)")


def icon(key: str) -> str:
    return f'<svg class="icon" viewBox="0 0 20 20" aria-hidden="true">{mark(10, 10, key)}</svg>'


def legend(points: list[Row]) -> str:
    items = "".join(
        f"<span>{icon(key)}{esc(label)} ({sum(p['key'] == key for p in points)})</span>"
        for key, label in VERDICTS.values()
    )
    return f'<div class="legend">{items}</div>'


def tooltip(point: Row) -> str:
    return esc(
        "\n".join(
            [
                point["name"],
                f"Verdict: {point['label']}",
                f"Best epoch: {point['epoch']}",
                f"p_forget: {point['p_forget']:.3g}",
                f"p_retain: {point['p_retain']:.3g}",
                f"Weakest family drop: {point['target_min_drop']:.2f} ({point['weakest_family']})",
                f"Lowest retention bound: {point['lowest_retention_bound']:.3f}",
            ]
        )
    )


def draw_points(points: list[Row], x: Scale, y: Scale) -> str:
    """Marks with a native tooltip and a hit target larger than the mark."""
    out = []
    for p in points:
        cx, cy = x(p["p_forget"]), y(p["p_retain"])
        out.append(
            f'<g><title>{tooltip(p)}</title><circle cx="{cx:.1f}" cy="{cy:.1f}" r="14" '
            f'fill="transparent"/>{mark(cx, cy, p["key"])}</g>'
        )
    return "".join(out)


def mark_boxes(points: list[Row], x: Scale, y: Scale) -> list[Box]:
    return [
        (x(p["p_forget"]) - 9, y(p["p_retain"]) - 9, x(p["p_forget"]) + 9, y(p["p_retain"]) + 9)
        for p in points
    ]


def overlaps(a: Box, b: Box) -> bool:
    return not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])


def place_labels(items: list[tuple[float, float, str]], obstacles: list[Box]) -> tuple[str, list[str]]:
    """Greedy placement: keep the first free position. Returns (svg, names that did not fit)."""
    boxes = list(obstacles)
    out: list[str] = []
    missed: list[str] = []
    for cx, cy, text in items:
        width = len(text) * CHAR_W
        chosen: tuple[float, float, int, Box] | None = None
        for dy in LABEL_OFFSETS:
            for side in (1, -1):
                x, y = cx + side * 12, cy + dy
                left = x if side > 0 else x - width
                box: Box = (left, y - LABEL_H / 2, left + width, y + LABEL_H / 2)
                inside = (
                    box[0] >= LABEL_BOUNDS[0]
                    and box[1] >= LABEL_BOUNDS[1]
                    and box[2] <= LABEL_BOUNDS[2]
                    and box[3] <= LABEL_BOUNDS[3]
                )
                if inside and not any(overlaps(box, other) for other in boxes):
                    chosen = (x, y, side, box)
                    break
            if chosen:
                break
        if chosen is None:
            missed.append(text)
            continue
        x, y, side, box = chosen
        boxes.append(box)
        if y != cy:
            out.append(
                f'<line x1="{cx:.1f}" y1="{cy:.1f}" x2="{x - side * 2:.1f}" y2="{y:.1f}" '
                'stroke="var(--muted)" stroke-width="1"/>'
            )
        anchor = "start" if side > 0 else "end"
        out.append(
            f'<text x="{x:.1f}" y="{y + 4:.1f}" text-anchor="{anchor}" font-size="12" '
            f'fill="var(--ink)">{esc(text)}</text>'
        )
    return "".join(out), missed


def axis_titles() -> str:
    return (
        f'<text x="{LEFT + PLOT_W / 2}" y="{HEIGHT - 10}" text-anchor="middle" font-size="12.5" '
        'fill="var(--ink2)">p_forget (smaller = stronger evidence of forgetting)</text>'
        f'<text transform="translate(16 {TOP + PLOT_H / 2}) rotate(-90)" text-anchor="middle" '
        'font-size="12.5" fill="var(--ink2)">p_retain (smaller = stronger evidence of retention)</text>'
    )


def y_tick(y: float, text: str) -> str:
    return (
        f'<line x1="{LEFT}" x2="{PLOT_RIGHT}" y1="{y:.1f}" y2="{y:.1f}" stroke="var(--grid)"/>'
        f'<text x="{LEFT - 8}" y="{y + 4:.1f}" text-anchor="end" font-size="11.5" fill="var(--ink2)">{text}</text>'
    )


def x_tick(x: float, text: str) -> str:
    return (
        f'<line x1="{x:.1f}" x2="{x:.1f}" y1="{PLOT_BOTTOM}" y2="{PLOT_BOTTOM + 5}" stroke="var(--muted)"/>'
        f'<text x="{x:.1f}" y="{PLOT_BOTTOM + 19}" text-anchor="middle" font-size="11.5" fill="var(--ink2)">{text}</text>'
    )


def baseline() -> str:
    return f'<line x1="{LEFT}" x2="{PLOT_RIGHT}" y1="{PLOT_BOTTOM}" y2="{PLOT_BOTTOM}" stroke="var(--muted)"/>'


def svg_chart(parts: list[str], aria_label: str) -> str:
    return (
        f'<svg class="chart" viewBox="0 0 {WIDTH} {HEIGHT}" role="img" '
        f'aria-label="{esc(aria_label)}">{"".join(parts)}</svg>'
    )


# --- charts -------------------------------------------------------------------------------


def full_chart(points: list[Row], alpha: float) -> tuple[str, list[str]]:
    """Every experiment on log axes, with the four verdict regions marked."""
    log_x = [math.log10(max(p["p_forget"], 1e-300)) for p in points]
    log_y = [math.log10(max(p["p_retain"], 1e-300)) for p in points]
    x_min = min(math.floor(min(log_x) / 10) * 10, int(X_BREAK) - 10)
    x_max, y_min, y_max = 0.08, min(math.floor(min(log_y)), -2), 0.09

    def fx(value: float) -> float:
        t = math.log10(max(value, 1e-300))
        if t <= X_BREAK:
            share = (t - x_min) / (X_BREAK - x_min) * X_BREAK_SHARE
        else:
            share = X_BREAK_SHARE + (t - X_BREAK) / (x_max - X_BREAK) * (1 - X_BREAK_SHARE)
        return LEFT + share * PLOT_W

    def fy(value: float) -> float:
        return PLOT_BOTTOM - (math.log10(max(value, 1e-300)) - y_min) / (y_max - y_min) * PLOT_H

    ax, ay = fx(alpha), fy(alpha)
    bx = fx(10.0**X_BREAK)
    parts = [
        f'<rect x="{LEFT}" y="{ay:.1f}" width="{ax - LEFT:.1f}" height="{PLOT_BOTTOM - ay:.1f}" fill="var(--region)"/>'
    ]
    parts += [y_tick(fy(10.0**d), f"{10.0**d:g}") for d in range(y_min, 1)]
    for d in [*range(x_min, int(X_BREAK), 10), -2, -1, 0]:
        parts.append(x_tick(fx(10.0**d), f"1e{d}" if d < -2 else f"{10.0**d:g}"))
    parts.append(
        f'<line x1="{bx:.1f}" x2="{bx:.1f}" y1="{TOP}" y2="{PLOT_BOTTOM}" stroke="var(--muted)" '
        'stroke-width="1" stroke-dasharray="1 4"/>'
        f'<text x="{bx - 5:.1f}" y="{TOP + 12}" text-anchor="end" font-size="11" '
        'fill="var(--muted)">axis compressed to the left</text>'
    )
    parts.append(baseline())
    dashed = 'stroke="var(--ink2)" stroke-width="1.2" stroke-dasharray="5 4"'
    parts.append(
        f'<line x1="{ax:.1f}" x2="{ax:.1f}" y1="{TOP}" y2="{PLOT_BOTTOM}" {dashed}/>'
        f'<line x1="{LEFT}" x2="{PLOT_RIGHT}" y1="{ay:.1f}" y2="{ay:.1f}" {dashed}/>'
        f'<text x="{ax + 5:.1f}" y="{PLOT_BOTTOM - 6}" font-size="11.5" fill="var(--ink2)">α = {alpha:g}</text>'
    )

    obstacles: list[Box] = []
    for x0, y0, text in (
        (LEFT + 10, ay - 8, "Collateral damage: forgotten, neighbours hurt"),
        (ax + 8, ay - 8, "Both failed"),
        (LEFT + 10, ay + 18, "Certified: both tests pass"),
        (ax + 8, ay + 18, "Not forgotten: neighbours safe"),
    ):
        parts.append(
            f'<text x="{x0:.1f}" y="{y0:.1f}" font-size="12" font-weight="600" fill="var(--ink2)">{esc(text)}</text>'
        )
        obstacles.append((x0, y0 - 11, x0 + len(text) * 6.8, y0 + 4))
    obstacles += mark_boxes(points, fx, fy)
    obstacles += [(ax + 4, PLOT_BOTTOM - 18, ax + 60, PLOT_BOTTOM - 2), (bx - 165, TOP, bx, TOP + 16)]

    parts.append(draw_points(points, fx, fy))

    # The "not forgotten" runs overlap here, so they share one callout and get their own chart.
    cluster = [p for p in points if p["key"] == "not_forgotten"]
    items = [(fx(p["p_forget"]), fy(p["p_retain"]), p["name"]) for p in points if p["key"] != "not_forgotten"]
    if cluster:
        items.append(
            (
                sum(fx(p["p_forget"]) for p in cluster) / len(cluster),
                sum(fy(p["p_retain"]) for p in cluster) / len(cluster),
                f"{len(cluster)} runs, see zoom below",
            )
        )
    labels, missed = place_labels(items, obstacles)
    parts += [labels, axis_titles()]
    return svg_chart(parts, "Scatter plot of p_forget against p_retain for each experiment, by verdict"), missed


def nice_ticks(low: float, high: float, count: int = 6) -> list[float]:
    raw = (high - low) / count
    magnitude = 10 ** math.floor(math.log10(raw))
    step = min((m * magnitude for m in (1, 2, 2.5, 5, 10) if m * magnitude >= raw), default=raw)
    return [k * step for k in range(math.ceil(low / step), math.floor(high / step) + 1)]


def padded(values: list[float]) -> tuple[float, float]:
    low, high = min(values), max(values)
    pad = max((high - low) * 0.14, abs(high) * 0.002)
    return low - pad, high + pad


def zoom_chart(cluster: list[Row]) -> tuple[str, list[str]]:
    """The "not forgotten" runs on linear axes, each one named."""
    x0, x1 = padded([p["p_forget"] for p in cluster])
    y0, y1 = padded([p["p_retain"] for p in cluster])

    def zx(value: float) -> float:
        return LEFT + (value - x0) / (x1 - x0) * PLOT_W

    def zy(value: float) -> float:
        return PLOT_BOTTOM - (value - y0) / (y1 - y0) * PLOT_H

    parts = [y_tick(zy(v), f"{v:.4g}") for v in nice_ticks(y0, y1)]
    parts += [x_tick(zx(v), f"{v:.4g}") for v in nice_ticks(x0, x1)]
    parts.append(baseline())
    parts.append(draw_points(cluster, zx, zy))
    labels, missed = place_labels(
        [(zx(p["p_forget"]), zy(p["p_retain"]), p["name"]) for p in cluster],
        mark_boxes(cluster, zx, zy),
    )
    parts += [labels, axis_titles()]
    return svg_chart(parts, "Zoomed scatter plot of the not forgotten experiments"), missed


def results_table(points: list[Row]) -> str:
    order = {key: i for i, (key, _) in enumerate(VERDICTS.values())}
    rows = []
    for p in sorted(points, key=lambda r: (order[r["key"]], r["p_afc"])):
        rows.append(
            f"<tr><td>{esc(p['name'])}</td><td>{icon(p['key'])}{esc(p['label'])}</td>"
            f"<td class=num>{p['epoch']}</td><td class=num>{format_p(p['p_forget'])}</td>"
            f"<td class=num>{format_p(p['p_retain'])}</td><td class=num>{format_p(p['p_afc'])}</td>"
            f"<td class=num>{p['target_min_drop']:.2f} ({esc(p['weakest_family'])})</td>"
            f"<td class=num>{p['lowest_retention_bound']:.3f}</td></tr>"
        )
    return (
        '<div class="scroll"><table><tr><th>Experiment</th><th>Verdict</th><th class=num>Best epoch</th>'
        "<th class=num>p_forget</th><th class=num>p_retain</th><th class=num>p_afc</th>"
        "<th class=num>Weakest family drop</th><th class=num>Lowest retention bound</th></tr>"
        f'{"".join(rows)}</table></div>'
    )


def excluded_table(excluded: list[Row]) -> str:
    rows = "".join(
        f"<tr><td>{esc(r['job_name'])}</td><td>{esc(r['verdict'] or '–')}</td>"
        f"<td class=num>{format_p(r['p_forget'])}</td></tr>"
        for r in excluded
    )
    return (
        '<div class="scroll"><table><tr><th>Experiment</th><th>Stored verdict</th>'
        f"<th class=num>p_forget</th></tr>{rows}</table></div>"
    )


def unlabelled_note(missed: list[str]) -> str:
    return f" Hover to identify unlabelled points: {', '.join(missed)}." if missed else ""


def render_page(points: list[Row], excluded: list[Row], alpha: float) -> str:
    certified = sum(p["key"] == "certified" for p in points)
    full_svg, full_missed = full_chart(points, alpha)
    body = [
        f"<h1>{certified} of {len(points)} experiments are certified</h1>",
        "<p>Each point is one experiment's best checkpoint. Dashed lines mark "
        f"α = {alpha:g}; lower left passes both tests. Both axes are logarithmic."
        f"{esc(unlabelled_note(full_missed))}</p>",
        legend(points),
        full_svg,
    ]

    cluster = [p for p in points if p["key"] == "not_forgotten"]
    if cluster:
        zoom_svg, zoom_missed = zoom_chart(cluster)
        body += [
            "<h2>Zoom: the runs that did not forget</h2>",
            f"<p>All {len(cluster)} have p_retain ≤ α but p_forget &gt; α: neighbours are safe and the "
            f"target's weakest family did not drop. Both axes are linear here.{esc(unlabelled_note(zoom_missed))}</p>",
            zoom_svg,
        ]

    body += ["<h2>All plotted experiments</h2>", "<p>Sorted by verdict, then p_afc.</p>", results_table(points)]
    if excluded:
        body += [
            f"<h2>Not plotted: {len(excluded)}</h2>",
            "<p>These rows lack a p_retain (no κ was set when they were scored) or a p_forget, "
            "so they cannot be placed on the chart.</p>",
            excluded_table(excluded),
        ]
    body.append(
        "<h2>Reading the verdicts</h2><p>Certified means the AFC criterion only. It does not show the "
        "model stopped producing the answer: the score includes the end token and cannot tell removal "
        "from garbled output. Certified runs still need greedy Q&amp;A and sampling checks.</p>"
    )
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>AFC Scatter</title>{STYLE}</head><body><main>{''.join(body)}</main></body></html>\n"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="scripts/afc_scatter_html.py")
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    parser.add_argument("--job-prefix", default="", help='only jobs starting with this, e.g. "phase2-"')
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)

    try:
        points, excluded, alpha = classify(load_rows(args.ledger, args.job_prefix))
    except (sqlite3.Error, ReportError) as exc:
        print(f"cannot build the page: {exc}", file=sys.stderr)
        return 1

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render_page(points, excluded, alpha), encoding="utf-8")
    print(f"{len(points)} plotted, {len(excluded)} not plotted, alpha={alpha} -> {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
