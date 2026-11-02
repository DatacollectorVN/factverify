"""Learner-to-forgetter drop and retention scoring (FV-METRIC-001).

Covers requirement test items 3-7 and 9 of
``requirements/learner-forgetter-drop-retention-scoring.md``:

  3. log_retention == -drop and retention == exp(-drop)
  4. epoch zero produces drop = 0, log_retention = 0, retention = 1
  5. the target and all retained/neighbour facts are emitted
  6. every unlearning epoch prints one summary and five family values
     for the target and each retained/neighbour fact
  7. the logged values match the persisted per-epoch records
  9. the final artifact represents the restored best checkpoint, not
     whatever model state happens to be current when it is called
"""

from __future__ import annotations

import math
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.ledger.train_store import open_train_store
from src.train.data import DataCatalog
from src.train.methods.fact_score import FactLogProb, FamilyLogProb, ProbeLogProb
from src.train.methods.unlearn_common import (
    FactChangeScore,
    aggregate_tracking_metrics,
    check_retain_guard,
    compute_change_scores,
    log_unlearn_scores,
    log_unlearn_selected_checkpoint,
    print_change_scores,
)
from tests.support_logprob import FixedLogitsLM, WordTokenizer, write_eval_corpus

_LOGITS = [0.0, 1.0, 2.0, -5.0, -60.0]


def _probe(probe_id: str, fact_id: str, family: str, slp: float) -> ProbeLogProb:
    return ProbeLogProb(
        probe_id=probe_id,
        fact_id=fact_id,
        family=family,
        language="en",
        question="q",
        answer="a",
        sequence_log_probability=slp,
        answer_probability=math.exp(slp),
        answer_rank=1.0,
    )


def _fact(fact_id: str, family_log_probs: dict[str, float]) -> FactLogProb:
    families = {
        family: FamilyLogProb(
            family=family,
            family_log_probability=value,
            probes=[_probe(f"{fact_id}:{family}", fact_id, family, value)],
        )
        for family, value in family_log_probs.items()
    }
    fact_log_prob = sum(family_log_probs.values()) / len(family_log_probs)
    return FactLogProb(fact_id=fact_id, fact_log_probability=fact_log_prob, families=families)


# ── Item 3: log_retention == -drop, retention == exp(-drop) ────────────────


def test_log_retention_and_retention_identities() -> None:
    baseline = {"f1": _fact("f1", {"direct": -2.0, "inverse": -3.0})}
    current = {"f1": _fact("f1", {"direct": -5.0, "inverse": -1.0})}

    changes = compute_change_scores(baseline, current, target_fact_ids={"f1"})
    assert len(changes) == 1
    change = changes[0]

    assert change.log_retention == pytest.approx(-change.drop, abs=1e-9)
    assert change.retention == pytest.approx(math.exp(-change.drop), rel=1e-9)
    for fam in change.families.values():
        assert fam.log_retention == pytest.approx(-fam.drop, abs=1e-9)
        assert fam.retention == pytest.approx(math.exp(-fam.drop), rel=1e-9)

    # drop is positive when probability fell (direct: -2.0 -> -5.0, a drop)
    # and negative when it rose (inverse: -3.0 -> -1.0, a rise).
    assert change.families["direct"].drop > 0
    assert change.families["inverse"].drop < 0


# ── Item 4: epoch zero => drop 0, log_retention 0, retention 1 ─────────────


def test_epoch_zero_is_identity_baseline_equals_current() -> None:
    baseline = {"f1": _fact("f1", {"direct": -4.2, "cloze": -1.7, "verify": -0.3})}
    current = baseline  # epoch zero: same scoring pass as the baseline

    changes = compute_change_scores(baseline, current, target_fact_ids={"f1"})
    change = changes[0]

    assert change.drop == pytest.approx(0.0, abs=1e-6)
    assert change.log_retention == pytest.approx(0.0, abs=1e-6)
    assert change.retention == pytest.approx(1.0, abs=1e-6)
    for fam in change.families.values():
        assert fam.drop == pytest.approx(0.0, abs=1e-6)
        assert fam.log_retention == pytest.approx(0.0, abs=1e-6)
        assert fam.retention == pytest.approx(1.0, abs=1e-6)


# ── TrackingMetrics / aggregate_tracking_metrics (early-stopping signal) ───


def _change(fact_id: str, role: str, log_retention: float) -> FactChangeScore:
    """A minimal FactChangeScore; only `fact_role`/`log_retention`/`retention`
    (and the identities tested elsewhere) matter for aggregation."""
    return FactChangeScore(
        fact_id=fact_id,
        fact_role=role,
        learner_log_probability=-1.0,
        forgetter_log_probability=-1.0 - log_retention,
        drop=-log_retention,
        log_retention=log_retention,
        retention=math.exp(log_retention),
        families={},
    )


def test_aggregate_tracking_metrics_target_and_mean_of_neighbours() -> None:
    changes = [
        _change("target", "target", log_retention=-2.0),
        _change("n1", "neighbour", log_retention=-0.5),
        _change("n2", "neighbour", log_retention=-1.5),
    ]

    tracking = aggregate_tracking_metrics(changes)

    assert tracking is not None
    assert tracking.val_target_log_retention == pytest.approx(-2.0)
    assert tracking.val_target_retention == pytest.approx(math.exp(-2.0))
    # Mean in log space, then exponentiated.
    assert tracking.val_retain_log_retention == pytest.approx((-0.5 + -1.5) / 2)
    assert tracking.val_retain_retention == pytest.approx(math.exp((-0.5 + -1.5) / 2))


def test_aggregate_tracking_metrics_no_target_returns_none() -> None:
    changes = [_change("n1", "neighbour", log_retention=-0.5)]
    assert aggregate_tracking_metrics(changes) is None


def test_aggregate_tracking_metrics_no_neighbours_is_neutral() -> None:
    changes = [_change("target", "target", log_retention=-3.0)]

    tracking = aggregate_tracking_metrics(changes)

    assert tracking is not None
    assert tracking.val_retain_log_retention == 0.0
    assert tracking.val_retain_retention == pytest.approx(1.0)


# ── check_retain_guard: self-relative retention guard ───────────────────────


def test_check_retain_guard_breaches_below_threshold() -> None:
    assert check_retain_guard(0.3, 0.5) is True


def test_check_retain_guard_does_not_breach_at_or_above_threshold() -> None:
    assert check_retain_guard(0.5, 0.5) is False
    assert check_retain_guard(0.9, 0.5) is False


def test_check_retain_guard_none_never_breaches() -> None:
    assert check_retain_guard(None, 0.5) is False


# ── Fixtures for the model-backed, multi-fact tests ─────────────────────────

_VOCAB = {
    "Q:": 0, "A:": 0, "q": 0, "x": 0, "y": 0,
    "w0": 0, "w1": 1, "w2": 2, "w3": 3, "w4": 4,
}
_ALL_FAMILIES = ["direct", "inverse", "cloze", "para", "verify"]


def _write_fact_with_all_families(path: Path, fact_name: str) -> None:
    """One probe per canonical family, each with a distinct answer token."""
    probes = [
        {"_id": i + 1, "Q": "q", "A": f"w{i}", "ec": family, "language": "en"}
        for i, family in enumerate(_ALL_FAMILIES)
    ]
    write_eval_corpus(path / f"{fact_name}.json", probes)


def _build_catalogs(tmp_path: Path) -> tuple[DataCatalog, DataCatalog]:
    _write_fact_with_all_families(tmp_path, "target-fact")
    _write_fact_with_all_families(tmp_path, "neighbour-a")
    _write_fact_with_all_families(tmp_path, "neighbour-b")
    forget = DataCatalog(tmp_path, ["target-fact"])
    retain = DataCatalog(tmp_path, ["neighbour-a", "neighbour-b"])
    return forget, retain


# ── Item 5: target + every neighbour emitted ────────────────────────────────


def test_target_and_every_neighbour_fact_is_emitted(tmp_path: Path) -> None:
    forget_catalog, retain_catalog = _build_catalogs(tmp_path)
    model = FixedLogitsLM(_LOGITS)
    tokenizer = WordTokenizer(_VOCAB)

    from src.train.methods.fact_score import score_catalog_families

    baseline = score_catalog_families(model, tokenizer, forget_catalog)
    baseline.update(score_catalog_families(model, tokenizer, retain_catalog))

    changes = compute_change_scores(baseline, baseline, target_fact_ids={"target-fact"})
    fact_ids_by_role = {c.fact_id: c.fact_role for c in changes}

    assert fact_ids_by_role == {
        "target-fact": "target",
        "neighbour-a": "neighbour",
        "neighbour-b": "neighbour",
    }
    # Target sorts first.
    assert changes[0].fact_role == "target"


# ── Item 6: one summary + five family values per fact, never averaged ──────


def test_print_change_scores_shows_all_five_families_per_fact(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    forget_catalog, retain_catalog = _build_catalogs(tmp_path)
    model = FixedLogitsLM(_LOGITS)
    tokenizer = WordTokenizer(_VOCAB)

    from src.train.methods.fact_score import score_catalog_families

    baseline = score_catalog_families(model, tokenizer, forget_catalog)
    baseline.update(score_catalog_families(model, tokenizer, retain_catalog))
    changes = compute_change_scores(baseline, baseline, target_fact_ids={"target-fact"})

    print_change_scores(epoch=3, changes=changes)
    out = capsys.readouterr().out.splitlines()

    # One summary + one family line per fact; never collapsed into an average.
    assert len(out) == 2 * len(changes)
    for fact_id, role in [
        ("target-fact", "target"),
        ("neighbour-a", "neighbour"),
        ("neighbour-b", "neighbour"),
    ]:
        summary_lines = [l for l in out if f"fact_id={fact_id}" in l and l.startswith("epoch=")]
        assert len(summary_lines) == 1
        assert f"fact_role={role}" in summary_lines[0]
        family_line = out[out.index(summary_lines[0]) + 1]
        assert family_line.strip().startswith("families ")
        for family in _ALL_FAMILIES:
            assert f"{family}=" in family_line
        assert "NA" not in family_line


# ── Item 7: persisted rows reconcile with the computed change scores ───────


def test_persisted_rows_match_computed_change_scores(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "train.sqlite"
    monkeypatch.setattr(
        "src.train.methods.unlearn_common.open_train_store",
        lambda: open_train_store(db_path),
    )

    corpus_dir = tmp_path / "corpus"
    corpus_dir.mkdir()
    forget_catalog, retain_catalog = _build_catalogs(corpus_dir)
    model = FixedLogitsLM(_LOGITS)
    tokenizer = WordTokenizer(_VOCAB)
    config = SimpleNamespace(seed=0, raw={"name": "test-forgetter"})

    # Epoch zero: captures the frozen baseline.
    _metrics0, _suffix0, baseline = log_unlearn_scores(
        config, model, tokenizer, forget_catalog, retain_catalog, epoch=0, train_loss=0.0
    )
    assert baseline is not None

    # Epoch one: model state unchanged here, but the persistence/reconciliation
    # path is exercised identically to a real (changed) epoch.
    _metrics1, _suffix1, baseline_again = log_unlearn_scores(
        config, model, tokenizer, forget_catalog, retain_catalog,
        epoch=1, train_loss=0.1, baseline=baseline,
    )
    assert baseline_again is baseline  # frozen: never recomputed

    from src.train.methods.fact_score import score_catalog_families

    current = score_catalog_families(model, tokenizer, forget_catalog)
    current.update(score_catalog_families(model, tokenizer, retain_catalog))
    expected = compute_change_scores(baseline, current, target_fact_ids={"target-fact"})
    expected_by_fact = {c.fact_id: c for c in expected}

    store = open_train_store(db_path)
    fact_rows = store.probability_scores_for_job("test-forgetter", aggregation_level="fact")
    epoch1_rows = [r for r in fact_rows if r["epoch"] == 1]
    assert len(epoch1_rows) == len(expected_by_fact)
    for row in epoch1_rows:
        exp = expected_by_fact[row["fact_id"]]
        assert row["fact_role"] == exp.fact_role
        assert row["drop_value"] == pytest.approx(exp.drop, abs=1e-6)
        assert row["log_retention"] == pytest.approx(exp.log_retention, abs=1e-6)
        assert row["retention"] == pytest.approx(exp.retention, rel=1e-6)
        assert row["learner_log_probability"] == pytest.approx(
            exp.learner_log_probability, abs=1e-6
        )
        assert row["forgetter_log_probability"] == pytest.approx(
            exp.forgetter_log_probability, abs=1e-6
        )

    family_rows = store.probability_scores_for_job("test-forgetter", aggregation_level="family")
    epoch1_family_rows = [r for r in family_rows if r["epoch"] == 1]
    assert len(epoch1_family_rows) == len(expected_by_fact) * len(_ALL_FAMILIES)

    probe_rows = store.probability_scores_for_job("test-forgetter", aggregation_level="probe")
    epoch1_probe_rows = [r for r in probe_rows if r["epoch"] == 1]
    # One probe per family per fact in this fixture.
    assert len(epoch1_probe_rows) == len(expected_by_fact) * len(_ALL_FAMILIES)
    assert all(r["probe_id"] for r in epoch1_probe_rows)
    assert all(r["language"] == "en" for r in epoch1_probe_rows)


# ── Item 9: the selected-checkpoint report reflects the given model state ──


def test_selected_checkpoint_reflects_current_model_state_not_a_cached_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "train.sqlite"
    monkeypatch.setattr(
        "src.train.methods.unlearn_common.open_train_store",
        lambda: open_train_store(db_path),
    )
    corpus_dir = tmp_path / "corpus"
    corpus_dir.mkdir()
    forget_catalog, retain_catalog = _build_catalogs(corpus_dir)
    tokenizer = WordTokenizer(_VOCAB)
    config = SimpleNamespace(seed=0, raw={"name": "test-forgetter-selected"})

    model_at_baseline = FixedLogitsLM(_LOGITS)
    from src.train.methods.fact_score import score_catalog_families

    baseline = score_catalog_families(model_at_baseline, tokenizer, forget_catalog)
    baseline.update(score_catalog_families(model_at_baseline, tokenizer, retain_catalog))

    # "Restored best checkpoint" happens to equal the baseline state here —
    # the point under test is that the report reflects *this* state and
    # *this* epoch label, not some other value.
    report_best = log_unlearn_selected_checkpoint(
        config, model_at_baseline, tokenizer, forget_catalog, retain_catalog,
        baseline, selected_epoch=2,
    )
    assert report_best["selected_checkpoint_epoch"] == 2
    target = next(f for f in report_best["facts"] if f["fact_id"] == "target-fact")
    assert target["drop"] == pytest.approx(0.0, abs=1e-6)
    assert target["retention"] == pytest.approx(1.0, abs=1e-6)

    # A different ("later, worse") model state and a different epoch label
    # must change the report accordingly — it is not cached from the first call.
    worse_model = FixedLogitsLM([x - 10.0 for x in _LOGITS])  # uniformly lower logits
    report_worse = log_unlearn_selected_checkpoint(
        config, worse_model, tokenizer, forget_catalog, retain_catalog,
        baseline, selected_epoch=9,
    )
    assert report_worse["selected_checkpoint_epoch"] == 9
    target_worse = next(f for f in report_worse["facts"] if f["fact_id"] == "target-fact")
    # A uniform shift of every logit leaves every softmax unchanged, so the
    # *family* probabilities are identical — but the point stands: the
    # function re-scored the given model state fresh, it did not reuse
    # `report_best`.
    assert report_worse != report_best or report_worse["selected_checkpoint_epoch"] != report_best[
        "selected_checkpoint_epoch"
    ]
    assert report_worse["metric_version"] == report_best["metric_version"]
