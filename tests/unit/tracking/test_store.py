"""Tests for TrackingStore: CRUD, status transitions, resume matching."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.services.common.errors import TrackingError
from src.services.tracking.store import TrackingStore
from src.services.tracking.types import AttemptStatus, CostRecord, LogicalRunId


def _make_run_id(**overrides: object) -> LogicalRunId:
    defaults = {
        "task": "train",
        "job_name": "block0-learner",
        "role": "learner",
        "seed": 3,
        "config_hash": "abc123",
        "model_identity": "model-hash",
        "data_manifest_digest": "data-hash",
        "code_revision": "deadbeef",
    }
    defaults.update(overrides)
    return LogicalRunId(**defaults)  # type: ignore[arg-type]


@pytest.fixture()
def store(tmp_path: Path) -> TrackingStore:
    s = TrackingStore.open(tmp_path / "test.sqlite")
    yield s
    s.close()


class TestLogicalRuns:
    def test_ensure_creates_run(self, store: TrackingStore) -> None:
        run_id = _make_run_id()
        digest = store.ensure_logical_run(run_id)
        assert digest == run_id.digest()
        assert len(digest) == 64

    def test_ensure_idempotent(self, store: TrackingStore) -> None:
        run_id = _make_run_id()
        d1 = store.ensure_logical_run(run_id)
        d2 = store.ensure_logical_run(run_id)
        assert d1 == d2

    def test_find_matching_run(self, store: TrackingStore) -> None:
        run_id = _make_run_id()
        store.ensure_logical_run(run_id)
        assert store.find_matching_run(run_id) == run_id.digest()

    def test_find_no_match(self, store: TrackingStore) -> None:
        run_id = _make_run_id()
        assert store.find_matching_run(run_id) is None


class TestAttempts:
    def test_create_attempt(self, store: TrackingStore) -> None:
        run_id = _make_run_id()
        digest = store.ensure_logical_run(run_id)
        attempt = store.create_attempt(
            attempt_id="att-1",
            run_id="run-1",
            run_digest=digest,
            config_hash="abc123",
        )
        assert attempt.status == AttemptStatus.PLANNED
        assert attempt.attempt_id == "att-1"

    def test_get_attempt(self, store: TrackingStore) -> None:
        run_id = _make_run_id()
        digest = store.ensure_logical_run(run_id)
        store.create_attempt(
            attempt_id="att-2",
            run_id="run-2",
            run_digest=digest,
            config_hash="abc123",
        )
        fetched = store.get_attempt("att-2")
        assert fetched is not None
        assert fetched.status == AttemptStatus.PLANNED

    def test_get_missing_attempt(self, store: TrackingStore) -> None:
        assert store.get_attempt("nonexistent") is None


class TestStatusTransitions:
    def test_planned_to_running(self, store: TrackingStore) -> None:
        run_id = _make_run_id()
        digest = store.ensure_logical_run(run_id)
        store.create_attempt(
            attempt_id="t1", run_id="r1", run_digest=digest, config_hash="h"
        )
        store.update_status("t1", AttemptStatus.RUNNING)
        att = store.get_attempt("t1")
        assert att is not None and att.status == AttemptStatus.RUNNING

    def test_running_to_succeeded(self, store: TrackingStore) -> None:
        run_id = _make_run_id()
        digest = store.ensure_logical_run(run_id)
        store.create_attempt(
            attempt_id="t2", run_id="r2", run_digest=digest, config_hash="h"
        )
        store.update_status("t2", AttemptStatus.RUNNING)
        store.update_status("t2", AttemptStatus.SUCCEEDED)
        att = store.get_attempt("t2")
        assert att is not None and att.status == AttemptStatus.SUCCEEDED

    def test_running_to_failed_with_error(self, store: TrackingStore) -> None:
        run_id = _make_run_id()
        digest = store.ensure_logical_run(run_id)
        store.create_attempt(
            attempt_id="t3", run_id="r3", run_digest=digest, config_hash="h"
        )
        store.update_status("t3", AttemptStatus.RUNNING)
        store.update_status(
            "t3", AttemptStatus.FAILED, error_summary="OOM"
        )
        att = store.get_attempt("t3")
        assert att is not None
        assert att.status == AttemptStatus.FAILED
        assert att.error_summary == "OOM"

    def test_running_to_interrupted(self, store: TrackingStore) -> None:
        run_id = _make_run_id()
        digest = store.ensure_logical_run(run_id)
        store.create_attempt(
            attempt_id="t4", run_id="r4", run_digest=digest, config_hash="h"
        )
        store.update_status("t4", AttemptStatus.RUNNING)
        store.update_status("t4", AttemptStatus.INTERRUPTED)
        att = store.get_attempt("t4")
        assert att is not None and att.status == AttemptStatus.INTERRUPTED

    def test_invalid_transition_raises(self, store: TrackingStore) -> None:
        run_id = _make_run_id()
        digest = store.ensure_logical_run(run_id)
        store.create_attempt(
            attempt_id="t5", run_id="r5", run_digest=digest, config_hash="h"
        )
        # PLANNED -> SUCCEEDED is invalid (must go through RUNNING)
        with pytest.raises(TrackingError, match="invalid transition"):
            store.update_status("t5", AttemptStatus.SUCCEEDED)

    def test_succeeded_is_terminal(self, store: TrackingStore) -> None:
        run_id = _make_run_id()
        digest = store.ensure_logical_run(run_id)
        store.create_attempt(
            attempt_id="t6", run_id="r6", run_digest=digest, config_hash="h"
        )
        store.update_status("t6", AttemptStatus.RUNNING)
        store.update_status("t6", AttemptStatus.SUCCEEDED)
        with pytest.raises(TrackingError, match="invalid transition"):
            store.update_status("t6", AttemptStatus.FAILED)

    def test_missing_attempt_raises(self, store: TrackingStore) -> None:
        with pytest.raises(TrackingError, match="not found"):
            store.update_status("ghost", AttemptStatus.RUNNING)


class TestCostRecording:
    def test_cost_stored_on_update(self, store: TrackingStore) -> None:
        run_id = _make_run_id()
        digest = store.ensure_logical_run(run_id)
        store.create_attempt(
            attempt_id="c1", run_id="r1", run_digest=digest, config_hash="h"
        )
        store.update_status("c1", AttemptStatus.RUNNING)
        cost = CostRecord(
            wall_clock_seconds=120.5,
            gpu_hours=0.5,
            peak_memory_bytes=4_000_000_000,
            examples=320,
            optimizer_steps=40,
        )
        store.update_status("c1", AttemptStatus.SUCCEEDED, cost=cost)
        att = store.get_attempt("c1")
        assert att is not None and att.cost is not None
        assert att.cost.wall_clock_seconds == 120.5
        assert att.cost.examples == 320
        assert att.cost.optimizer_steps == 40


class TestResumeIdentity:
    """Stale-resume rejection: changing any identity component → different run."""

    def test_same_identity_matches(self, store: TrackingStore) -> None:
        run_id = _make_run_id()
        store.ensure_logical_run(run_id)
        assert store.find_matching_run(run_id) is not None

    def test_different_config_hash_no_match(self, store: TrackingStore) -> None:
        run_id = _make_run_id()
        store.ensure_logical_run(run_id)
        altered = _make_run_id(config_hash="different")
        assert store.find_matching_run(altered) is None

    def test_different_model_identity_no_match(self, store: TrackingStore) -> None:
        run_id = _make_run_id()
        store.ensure_logical_run(run_id)
        altered = _make_run_id(model_identity="different-model")
        assert store.find_matching_run(altered) is None

    def test_different_data_digest_no_match(self, store: TrackingStore) -> None:
        run_id = _make_run_id()
        store.ensure_logical_run(run_id)
        altered = _make_run_id(data_manifest_digest="different-data")
        assert store.find_matching_run(altered) is None

    def test_different_code_revision_no_match(self, store: TrackingStore) -> None:
        run_id = _make_run_id()
        store.ensure_logical_run(run_id)
        altered = _make_run_id(code_revision="different-commit")
        assert store.find_matching_run(altered) is None

    def test_different_seed_no_match(self, store: TrackingStore) -> None:
        run_id = _make_run_id()
        store.ensure_logical_run(run_id)
        altered = _make_run_id(seed=999)
        assert store.find_matching_run(altered) is None

    def test_find_succeeded_attempt(self, store: TrackingStore) -> None:
        run_id = _make_run_id()
        digest = store.ensure_logical_run(run_id)
        store.create_attempt(
            attempt_id="a1", run_id="r1", run_digest=digest, config_hash="h"
        )
        store.update_status("a1", AttemptStatus.RUNNING)
        store.update_status("a1", AttemptStatus.SUCCEEDED)
        found = store.find_succeeded_attempt(digest)
        assert found is not None
        assert found.status == AttemptStatus.SUCCEEDED

    def test_no_succeeded_attempt(self, store: TrackingStore) -> None:
        run_id = _make_run_id()
        digest = store.ensure_logical_run(run_id)
        store.create_attempt(
            attempt_id="a2", run_id="r2", run_digest=digest, config_hash="h"
        )
        store.update_status("a2", AttemptStatus.RUNNING)
        store.update_status("a2", AttemptStatus.FAILED, error_summary="boom")
        assert store.find_succeeded_attempt(digest) is None


class TestMetricsAndArtifacts:
    def test_record_epoch_metric(self, store: TrackingStore) -> None:
        run_id = _make_run_id()
        digest = store.ensure_logical_run(run_id)
        store.create_attempt(
            attempt_id="m1", run_id="r1", run_digest=digest, config_hash="h"
        )
        store.record_epoch_metric("m1", 1, "loss", 0.5)
        store.record_epoch_metric("m1", 2, "loss", 0.3)
        # No assertion on return — just verify no exception

    def test_record_artifact(self, store: TrackingStore) -> None:
        run_id = _make_run_id()
        digest = store.ensure_logical_run(run_id)
        store.create_attempt(
            attempt_id="a1", run_id="r1", run_digest=digest, config_hash="h"
        )
        store.record_artifact(
            "a1",
            "checkpoint",
            "/path/to/best",
            digest="sha256:abc",
            size_bytes=1024,
        )
