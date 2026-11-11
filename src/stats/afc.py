"""AFC verdict: ``p_forget``, ``p_retain`` and their combination.

Implements ``docs/p_forget_p_retain_spec.md`` on family-group drop and
retention scores. The number of neighbours comes from the input, so ``n`` and
every degree of freedom are derived rather than fixed.

``kappa`` is optional. Without it ``p_retain`` is not tested and a checkpoint
cannot be certified, because the spec's verdict requires both tests. The
retention lower bound is reported either way.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
from scipy import stats as _scipy_stats

from src.stats.errors import StatsError

FAMILIES: tuple[str, ...] = ("direct", "inverse", "cloze", "para", "verify")

CERTIFIED = "certified"
NOT_FORGOTTEN = "not certified: not forgotten"
COLLATERAL_DAMAGE = "not certified: collateral damage"
BOTH_FAILED = "not certified: both failed"
FORGET_SHOWN_RETAIN_UNTESTED = "forgetting shown; retention not tested"
NOT_FORGOTTEN_RETAIN_UNTESTED = "not forgotten; retention not tested"
DEGENERATE_CONTROL = "not certified: degenerate control"

_IDENTITY_TOLERANCE = 1e-9
_DUPLICATE_RELATIVE_TOLERANCE = 1e-9


@dataclass(frozen=True)
class AFCSettings:
    """The frozen test parameters. ``kappa`` is None when retention is untested."""

    alpha: float
    kappa: float | None = None

    @classmethod
    def from_mapping(cls, section: Any) -> AFCSettings:
        """Parse a config ``afc`` section. ``alpha`` is required, ``kappa`` optional."""
        if not isinstance(section, Mapping):
            raise StatsError("afc must be a mapping")
        unknown = sorted(set(section) - {"alpha", "kappa"})
        if unknown:
            raise StatsError(f"afc has unknown field {unknown[0]!r}")
        if "alpha" not in section:
            raise StatsError("afc.alpha is required")
        settings = cls(
            alpha=_number(section["alpha"], "afc.alpha"),
            kappa=_optional_number(section.get("kappa"), "afc.kappa"),
        )
        _require_probability(settings.alpha, "alpha")
        if settings.kappa is not None:
            _require_probability(settings.kappa, "kappa")
        return settings


@dataclass(frozen=True)
class AFCResult:
    """Every intermediate of one AFC evaluation, in family and neighbour order."""

    t: float
    m: float
    s: float
    T_forget: float
    p_forget: float
    weakest_family_target: str
    T_retain: list[float] | None
    p_retain_j: list[float] | None
    p_retain: float | None
    weakest_neighbour: int | None
    p_afc: float
    forget_ok: bool
    retain_ok: bool | None
    certified: bool
    verdict: str
    alpha: float
    kappa: float | None
    J: int
    n: int
    df_forget: int
    df_retain: int
    y_bar_j: list[float]
    s_j: list[float]
    se_j: list[float]
    mean_retention_j: list[float]
    retain_lower_bound_j: list[float]
    lowest_bound_neighbour: int
    flags: list[str]


def crawford_howell(t: float, m: float, s: float, n: int) -> tuple[float, float]:
    """Return ``(T_forget, p_forget)`` for a candidate against ``n`` controls."""
    if n < 2:
        raise StatsError("n must be at least 2")
    if s <= 0:
        raise StatsError("degenerate_control")
    statistic = (t - m) / (s * math.sqrt(1 + 1 / n))
    return statistic, float(_scipy_stats.t.sf(statistic, n - 1))


def afc(
    d_target: Mapping[str, float],
    d_nb: Any,
    r_nb: Any,
    *,
    alpha: float,
    kappa: float | None = None,
    families: Sequence[str] = FAMILIES,
) -> AFCResult:
    """Evaluate one checkpoint. Invalid input raises ``StatsError``, not a p-value."""
    retentions = np.asarray(r_nb, dtype=float)
    if not np.isfinite(retentions).all() or (retentions <= 0).any():
        raise StatsError("r_nb must be positive and finite")
    return _evaluate(d_target, d_nb, np.log(retentions), alpha, kappa, families)


def _evaluate(
    d_target: Mapping[str, float],
    d_nb: Any,
    log_r_nb: Any,
    alpha: float,
    kappa: float | None,
    families: Sequence[str],
) -> AFCResult:
    target, drops, y = _validated(d_target, d_nb, log_r_nb, alpha, kappa, families)
    flags: list[str] = []

    weakest = int(np.argmin(target))
    candidate = float(target[weakest])
    control = drops.ravel()
    n = control.size
    mean = float(control.mean())
    sd = _sample_sd(control)
    if sd == 0:
        flags.append("degenerate_control")
        statistic, p_forget = math.nan, math.nan
    else:
        statistic, p_forget = crawford_howell(candidate, mean, sd, n)

    df_retain = len(families) - 1
    y_bar = y.mean(axis=1)
    s_j = np.array([_sample_sd(row) for row in y])
    se_j = s_j / math.sqrt(len(families))
    critical = float(_scipy_stats.t.isf(alpha, df_retain))
    bounds = np.exp(y_bar - critical * se_j)

    t_retain, p_retain_j, p_retain, weakest_neighbour = None, None, None, None
    if kappa is not None:
        t_retain, p_retain_j = _retention_tests(
            y_bar, se_j, math.log(kappa), df_retain, flags
        )
        weakest_neighbour = int(np.argmax(p_retain_j))
        p_retain = p_retain_j[weakest_neighbour]

    forget_ok = not math.isnan(p_forget) and p_forget <= alpha
    retain_ok = None if p_retain is None else p_retain <= alpha
    p_afc = _combined_p(p_forget, p_retain)
    return AFCResult(
        t=candidate,
        m=mean,
        s=sd,
        T_forget=statistic,
        p_forget=p_forget,
        weakest_family_target=families[weakest],
        T_retain=t_retain,
        p_retain_j=p_retain_j,
        p_retain=p_retain,
        weakest_neighbour=weakest_neighbour,
        p_afc=p_afc,
        forget_ok=forget_ok,
        retain_ok=retain_ok,
        certified=forget_ok and retain_ok is True,
        verdict=_verdict(forget_ok, retain_ok, "degenerate_control" in flags),
        alpha=alpha,
        kappa=kappa,
        J=drops.shape[0],
        n=n,
        df_forget=n - 1,
        df_retain=df_retain,
        y_bar_j=y_bar.tolist(),
        s_j=s_j.tolist(),
        se_j=se_j.tolist(),
        mean_retention_j=np.exp(y_bar).tolist(),
        retain_lower_bound_j=bounds.tolist(),
        lowest_bound_neighbour=int(np.argmin(bounds)),
        flags=flags,
    )


def afc_from_report(
    report: Mapping[str, Any],
    declared_neighbours: Sequence[str],
    settings: AFCSettings,
    *,
    families: Sequence[str] = FAMILIES,
) -> dict[str, Any]:
    """Run AFC on a ``drop_retention.json`` payload and return a JSON-ready dict.

    ``declared_neighbours`` is the target fact's own ``neighbourhoods`` list and
    fixes J. A declared neighbour without scores is an error. Scored facts that
    were not declared are ignored and listed. Identical neighbours are kept and
    listed, because the declared set is what the test is defined on.
    """
    if not declared_neighbours:
        raise StatsError("target fact declares no neighbours")
    if len(set(declared_neighbours)) != len(declared_neighbours):
        raise StatsError("declared neighbours contain a repeated id")
    facts = report.get("facts")
    if not isinstance(facts, list) or not facts:
        raise StatsError("report has no facts")
    targets = [fact for fact in facts if fact.get("fact_role") == "target"]
    if len(targets) != 1:
        raise StatsError(
            f"report must have exactly one target fact, found {len(targets)}"
        )
    scored = {
        fact["fact_id"]: fact for fact in facts if fact.get("fact_role") == "neighbour"
    }
    missing = [fact_id for fact_id in declared_neighbours if fact_id not in scored]
    if missing:
        raise StatsError(f"declared neighbour has no scores: {missing[0]}")

    target = targets[0]
    d_target = {family: _cell(target, family, "drop") for family in families}
    d_nb = [
        [_cell(scored[fact_id], family, "drop") for family in families]
        for fact_id in declared_neighbours
    ]
    r_nb = [
        [_cell(scored[fact_id], family, "retention") for family in families]
        for fact_id in declared_neighbours
    ]
    # Log retention is used directly: retention underflows to 0 past a drop of ~745.
    log_r_nb = [
        [_cell(scored[fact_id], family, "log_retention") for family in families]
        for fact_id in declared_neighbours
    ]
    result = _evaluate(
        d_target, d_nb, log_r_nb, settings.alpha, settings.kappa, families
    )
    return {
        "job_name": report.get("job_name"),
        "seed": report.get("seed"),
        "metric_version": report.get("metric_version"),
        "selected_checkpoint_epoch": report.get("selected_checkpoint_epoch"),
        "selected_below_guard": bool(report.get("selected_below_guard", False)),
        "target_fact": target["fact_id"],
        "neighbours": list(declared_neighbours),
        "ignored_neighbours": sorted(set(scored) - set(declared_neighbours)),
        "duplicate_neighbours": _duplicates(declared_neighbours, d_nb),
        "families": list(families),
        "inputs": {"d_target": d_target, "d_nb": d_nb, "r_nb": r_nb},
        **result_to_json(result),
    }


def certify_report(
    report: Mapping[str, Any],
    declared_neighbours: Sequence[str],
    settings: AFCSettings,
    *,
    families: Sequence[str] = FAMILIES,
) -> dict[str, Any]:
    """Like :func:`afc_from_report`, but a rejected input becomes ``{"error": ...}``."""
    try:
        return afc_from_report(report, declared_neighbours, settings, families=families)
    except StatsError as exc:
        return {
            "job_name": report.get("job_name"),
            "selected_checkpoint_epoch": report.get("selected_checkpoint_epoch"),
            "error": exc.message,
        }


def summary_line(payload: Mapping[str, Any]) -> str:
    """One log line for a :func:`certify_report` payload."""
    if "error" in payload:
        return f"error: {payload['error']}"
    p_forget = "n/a" if payload["p_forget"] is None else f"{payload['p_forget']:.3g}"
    parts = [
        f"verdict={payload['verdict']}",
        f"t={payload['t']:.3f}",
        f"weakest_family={payload['weakest_family_target']}",
        f"p_forget={p_forget}",
    ]
    if payload["p_retain"] is not None:
        parts.append(f"p_retain={payload['p_retain']:.3g}")
    parts.append(f"lowest_retention_bound={min(payload['retain_lower_bound_j']):.3g}")
    if payload.get("selected_below_guard"):
        parts.append("selected_below_guard")
    return "  ".join(parts)


def result_to_json(result: AFCResult) -> dict[str, Any]:
    """Return the result as JSON-safe values. NaN and infinities become None."""
    return {key: _json_safe(value) for key, value in asdict(result).items()}


def _validated(
    d_target: Mapping[str, float],
    d_nb: Any,
    log_r_nb: Any,
    alpha: float,
    kappa: float | None,
    families: Sequence[str],
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    _require_probability(alpha, "alpha")
    if kappa is not None:
        _require_probability(kappa, "kappa")
    if len(families) < 2 or len(set(families)) != len(families):
        raise StatsError("families must be at least two distinct names")
    if set(d_target) != set(families):
        raise StatsError("d_target must have one value per family")
    target = np.array([d_target[family] for family in families], dtype=float)
    drops = np.asarray(d_nb, dtype=float)
    log_retentions = np.asarray(log_r_nb, dtype=float)
    if drops.ndim != 2 or drops.shape[0] < 1 or drops.shape[1] != len(families):
        raise StatsError("d_nb must have shape (J, number of families) with J >= 1")
    if log_retentions.shape != drops.shape:
        raise StatsError("r_nb must have the same shape as d_nb")
    if not np.isfinite(target).all():
        raise StatsError("d_target must be finite")
    if not np.isfinite(drops).all():
        raise StatsError("d_nb must be finite")
    if not np.isfinite(log_retentions).all():
        raise StatsError("ln r must be finite")
    allowed = _IDENTITY_TOLERANCE * np.maximum(1.0, np.abs(drops))
    if (np.abs(log_retentions + drops) > allowed).any():
        raise StatsError("ln r must equal -d for every neighbour cell")
    return target, drops, log_retentions


def _retention_tests(
    y_bar: np.ndarray,
    se_j: np.ndarray,
    mu0: float,
    df: int,
    flags: list[str],
) -> tuple[list[float], list[float]]:
    statistics: list[float] = []
    p_values: list[float] = []
    for j, (mean, se) in enumerate(zip(y_bar.tolist(), se_j.tolist())):
        if se == 0:
            flags.append(f"zero_se_neighbour_{j}")
            statistics.append(math.inf if mean > mu0 else -math.inf)
            p_values.append(0.0 if mean > mu0 else 1.0)
            continue
        statistic = (mean - mu0) / se
        statistics.append(statistic)
        p_values.append(float(_scipy_stats.t.sf(statistic, df)))
    return statistics, p_values


def _sample_sd(values: np.ndarray) -> float:
    """Sample SD, exactly 0 for identical values (rounding would make it ~1e-18)."""
    return 0.0 if np.ptp(values) == 0 else float(values.std(ddof=1))


def _combined_p(p_forget: float, p_retain: float | None) -> float:
    if math.isnan(p_forget):
        return math.nan
    return p_forget if p_retain is None else max(p_forget, p_retain)


def _verdict(forget_ok: bool, retain_ok: bool | None, degenerate: bool) -> str:
    if degenerate:
        return DEGENERATE_CONTROL
    if retain_ok is None:
        return (
            FORGET_SHOWN_RETAIN_UNTESTED if forget_ok else NOT_FORGOTTEN_RETAIN_UNTESTED
        )
    if forget_ok and retain_ok:
        return CERTIFIED
    if retain_ok:
        return NOT_FORGOTTEN
    return COLLATERAL_DAMAGE if forget_ok else BOTH_FAILED


def _cell(fact: Mapping[str, Any], family: str, field: str) -> float:
    families = fact.get("families") or {}
    if family not in families or families[family].get(field) is None:
        raise StatsError(f"{fact.get('fact_id')} has no {field} for family {family}")
    return float(families[family][field])


def _duplicates(ids: Sequence[str], d_nb: Iterable[Iterable[float]]) -> list[list[str]]:
    rows = [np.asarray(list(row), dtype=float) for row in d_nb]
    groups: list[list[int]] = []
    for index, row in enumerate(rows):
        for group in groups:
            if np.allclose(
                rows[group[0]], row, rtol=_DUPLICATE_RELATIVE_TOLERANCE, atol=0.0
            ):
                group.append(index)
                break
        else:
            groups.append([index])
    return [[ids[i] for i in group] for group in groups if len(group) > 1]


def _require_probability(value: float, name: str) -> None:
    if not 0 < value < 1:
        raise StatsError(f"{name} must be strictly between 0 and 1")


def _number(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise StatsError(f"{name} must be a number")
    return float(value)


def _optional_number(value: Any, name: str) -> float | None:
    return None if value is None else _number(value, name)


def _json_safe(value: Any) -> Any:
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value
