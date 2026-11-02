"""Worked drop/retention cases for FV-METRIC-001 (drop-retention-v1).

Four synthetic forgetter outcomes for one real target fact and its five
dataset neighbours, scored with exactly the rules in
``src/train/methods/unlearn_common.py``:

    family drop      d^phi = ln Pbar_L(.,phi) - ln Pbar_F(.,phi)
    fact drop        d     = mean_phi d^phi      (= ln Pbar_L - ln Pbar_F)
    retention        r     = exp(-d)
    retain aggregate ln r_retain = mean_j ln r_gj ; r_retain = exp(.)

Inputs are family-group probabilities Pbar (Level 2 of the draw.io tab:
geometric mean over the K probes of one family). Numbers are illustrative.

Verdict thresholds are ASSUMPTIONS for illustration (the requirements doc
explicitly leaves scientific pass/fail thresholds out of scope):
    target forgotten : r_f  <= TARGET_R_MAX   (drop >= ln 10 = 2.303)
    neighbour kept   : r_gj >= NEIGH_R_MIN    (drop <= 0.223, delta = 0.2 damage line)
    guard rail       : r_retain < RETAIN_GUARD stops training (config default 0.5)

Run:  python scripts/drop_retention_cases.py            (pure python)
      uv run python scripts/drop_retention_cases.py     (also cross-checks
                                                         against src/ if torch is installed)
"""
from __future__ import annotations

import math

FAMILIES = ["direct", "inverse", "cloze", "para", "verify"]
TARGET_R_MAX = 0.10
NEIGH_R_MIN = 0.80
RETAIN_GUARD = 0.50

TARGET = ("f", "full_0_jaime_vasquez_hails_from_santiago_chile", "Jaime Vasquez — birthplace — Santiago, Chile")
NEIGHBOURS = [
    ("g1", "full_0_jaime_vasquez_specializes_in_true_crime_genre", "Jaime Vasquez — genre — true crime (same subject)"),
    ("g2", "full_21_chukwu_akabueze_born_in_lagos_nigeria", "Chukwu Akabueze — birthplace — Lagos, Nigeria"),
    ("g3", "full_60_anara_yusifova_born_in_baku_azerbaijan", "Anara Yusifova — birthplace — Baku, Azerbaijan"),
    ("g4", "full_80_jordan_sinclair_hails_from_kingston_jamaica", "Jordan Sinclair — birthplace — Kingston, Jamaica"),
    ("g5", "full_81_jordan_sinclair_born_in_kingston_jamaica", "Jordan Sinclair — birthplace — Kingston, Jamaica (duplicate triple)"),
]

# Learner baseline L (epoch 0): Pbar_L per family [direct, inverse, cloze, para, verify]
LEARNER = {
    "f":  [0.80, 0.55, 0.75, 0.70, 0.95],
    "g1": [0.72, 0.60, 0.78, 0.66, 0.93],
    "g2": [0.85, 0.62, 0.80, 0.74, 0.96],
    "g3": [0.78, 0.58, 0.76, 0.70, 0.94],
    "g4": [0.82, 0.64, 0.79, 0.72, 0.95],
    "g5": [0.81, 0.63, 0.78, 0.71, 0.95],
}

_TARGET_FORGOTTEN = [0.010, 0.020, 0.015, 0.020, 0.25]
_TARGET_KEPT_GOOD = [0.76, 0.52, 0.72, 0.66, 0.94]   # barely moved
_TARGET_KEPT_BAD3 = [0.74, 0.50, 0.70, 0.65, 0.93]   # barely moved
_NEIGH_UNCHANGED = {
    "g1": [0.66, 0.55, 0.72, 0.60, 0.90],  # same-subject neighbour takes a small hit
    "g2": [0.84, 0.61, 0.79, 0.73, 0.96],
    "g3": [0.77, 0.57, 0.75, 0.69, 0.94],
    "g4": [0.81, 0.63, 0.78, 0.71, 0.95],
    "g5": [0.80, 0.62, 0.77, 0.70, 0.95],
}
_NEIGH_COLLAPSED = {
    "g1": [0.02, 0.03, 0.04, 0.03, 0.35],
    "g2": [0.10, 0.08, 0.12, 0.10, 0.50],
    "g3": [0.12, 0.09, 0.10, 0.11, 0.55],
    "g4": [0.06, 0.05, 0.07, 0.06, 0.45],
    "g5": [0.06, 0.05, 0.07, 0.06, 0.45],
}

CASES = {
    "good":  ("Good forgetter", "forgets target, keeps neighbours",
              {"f": _TARGET_FORGOTTEN, **_NEIGH_UNCHANGED}),
    "bad1":  ("Bad forgetter 1 (over-forgetting)", "forgets target AND neighbours",
              {"f": _TARGET_FORGOTTEN, **_NEIGH_COLLAPSED}),
    "bad2":  ("Bad forgetter 2 (no-op)", "fails to forget target; neighbours unchanged",
              {"f": _TARGET_KEPT_GOOD, **_NEIGH_UNCHANGED}),
    "bad3":  ("Bad forgetter 3 (misdirected)", "fails to forget target, forgets neighbours",
              {"f": _TARGET_KEPT_BAD3, **_NEIGH_COLLAPSED}),
}


def score(learner: list[float], forgetter: list[float]) -> dict:
    fam = {}
    for name, pl, pf in zip(FAMILIES, learner, forgetter):
        d = math.log(pl) - math.log(pf)
        fam[name] = {"PL": pl, "PF": pf, "drop": d, "log_r": -d, "r": math.exp(-d)}
    # fact log prob = mean of family log probs  ->  fact drop = mean family drop
    lpl = sum(math.log(p) for p in learner) / len(learner)
    lpf = sum(math.log(p) for p in forgetter) / len(forgetter)
    d = lpl - lpf
    return {"families": fam, "PL": math.exp(lpl), "PF": math.exp(lpf), "drop": d, "log_r": -d, "r": math.exp(-d)}


def run_case(key: str) -> dict:
    title, desc, forg = CASES[key]
    t = score(LEARNER["f"], forg["f"])
    nb = {g: score(LEARNER[g], forg[g]) for g, _, _ in NEIGHBOURS}
    retain_log_r = sum(s["log_r"] for s in nb.values()) / len(nb)
    retain_r = math.exp(retain_log_r)
    forgot = t["r"] <= TARGET_R_MAX
    kept = sum(s["r"] >= NEIGH_R_MIN for s in nb.values())
    if forgot and kept == len(nb):
        verdict = "PASS — target forgotten, all neighbours kept"
    elif forgot:
        verdict = f"FAIL — target forgotten but only {kept}/{len(nb)} neighbours kept (collateral damage)"
    elif kept == len(nb):
        verdict = "FAIL — target NOT forgotten (no effective unlearning)"
    else:
        verdict = f"FAIL — target NOT forgotten and only {kept}/{len(nb)} neighbours kept (wrong knowledge removed)"
    return {"title": title, "desc": desc, "target": t, "neigh": nb,
            "retain_log_r": retain_log_r, "retain_r": retain_r,
            "guard_stop": retain_r < RETAIN_GUARD, "verdict": verdict}


def fmt_case(key: str) -> str:
    c = run_case(key)
    t = c["target"]
    out = [f"### {c['title']} — {c['desc']}", ""]
    out.append("**Target f, family level**")
    out.append("")
    out.append("| φ | P̄_L | P̄_F | d̄^φ (drop) | ln r̄^φ | r̄^φ (retention) |")
    out.append("|---|---:|---:|---:|---:|---:|")
    for name, v in t["families"].items():
        out.append(f"| {name} | {v['PL']:.3f} | {v['PF']:.3f} | {v['drop']:.4f} | {v['log_r']:.4f} | {v['r']:.4f} |")
    out.append(f"| **fact f** | {t['PL']:.4f} | {t['PF']:.4f} | **{t['drop']:.4f}** | {t['log_r']:.4f} | **{t['r']:.4f}** |")
    out.append("")
    out.append("**Neighbours g_j (fact level; family drops in brackets: direct/inverse/cloze/para/verify)**")
    out.append("")
    out.append("| g_j | fact | d̄_gj | r̄_gj | kept (r̄ ≥ 0.80)? | family drops |")
    out.append("|---|---|---:|---:|:---:|---|")
    for g, _fid, label in NEIGHBOURS:
        s = c["neigh"][g]
        fams = " / ".join(f"{v['drop']:.3f}" for v in s["families"].values())
        out.append(f"| {g} | {label} | {s['drop']:.4f} | {s['r']:.4f} | {'yes' if s['r'] >= NEIGH_R_MIN else 'NO'} | {fams} |")
    out.append("")
    out.append(f"- Target: d̄_f = {t['drop']:.4f}, r̄_f = {t['r']:.4f} → {'forgotten' if t['r'] <= TARGET_R_MAX else 'NOT forgotten'} (needs r̄_f ≤ {TARGET_R_MAX})")
    out.append(f"- Retain aggregate: ln r̄_retain = {c['retain_log_r']:.4f}, r̄_retain = {c['retain_r']:.4f}"
               f" → guard rail (< {RETAIN_GUARD}) {'TRIGGERS early stop' if c['guard_stop'] else 'does not trigger'}")
    out.append(f"- **Verdict: {c['verdict']}**")
    return "\n".join(out)


def summary_table() -> str:
    rows = ["| Case | d̄_f | r̄_f | mean d̄_g | r̄_retain | neighbours kept | guard rail | verdict |",
            "|---|---:|---:|---:|---:|:---:|:---:|---|"]
    for key in CASES:
        c = run_case(key)
        kept = sum(s["r"] >= NEIGH_R_MIN for s in c["neigh"].values())
        rows.append(f"| {c['title']} | {c['target']['drop']:.3f} | {c['target']['r']:.4f} | {-c['retain_log_r']:.3f} | "
                    f"{c['retain_r']:.4f} | {kept}/{len(c['neigh'])} | {'STOP' if c['guard_stop'] else 'ok'} | {c['verdict'].split(' — ')[0]} |")
    return "\n".join(rows)


def cross_check_against_src() -> str:
    """Re-score every case with the real compute_change_scores/aggregate_tracking_metrics."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    try:
        from src.train.methods.fact_score import FactLogProb, FamilyLogProb
        from src.train.methods.unlearn_common import aggregate_tracking_metrics, compute_change_scores
    except Exception as exc:  # torch / click not installed
        return f"(cross-check against src/ skipped: {type(exc).__name__}: {exc})"

    def flp(fact_id, probs):
        fams = {n: FamilyLogProb(family=n, family_log_probability=math.log(p)) for n, p in zip(FAMILIES, probs)}
        return FactLogProb(fact_id=fact_id, fact_log_probability=sum(f.family_log_probability for f in fams.values()) / 5, families=fams)

    ids = {"f": TARGET[1], **{g: fid for g, fid, _ in NEIGHBOURS}}
    for key, (_t, _d, forg) in CASES.items():
        base = {ids[k]: flp(ids[k], LEARNER[k]) for k in ids}
        cur = {ids[k]: flp(ids[k], forg[k]) for k in ids}
        tm = aggregate_tracking_metrics(compute_change_scores(base, cur, {TARGET[1]}))
        mine = run_case(key)
        assert math.isclose(tm.val_target_retention, mine["target"]["r"], rel_tol=1e-12), key
        assert math.isclose(tm.val_retain_retention, mine["retain_r"], rel_tol=1e-12), key
    return "(cross-check against src/ compute_change_scores + aggregate_tracking_metrics: all 4 cases match)"


if __name__ == "__main__":
    print("## Summary\n")
    print(summary_table())
    print()
    for key in CASES:
        print(fmt_case(key))
        print()
    print(cross_check_against_src())
