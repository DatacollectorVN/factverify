"""FV-EVAL-001 through FV-EVAL-014."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from src.eval import evaluate_case
from src.eval.budget import Accountant, start_run
from src.eval.channels import permit
from src.eval.errors import BudgetExhaustedError, FactVerifyEvalError
from src.eval.gateway import illegal_calls_in_source, illegal_model_calls
from src.eval.native import score_native
from src.eval.semantic import require_primary, select_equivalence
from src.eval.spec_load import (
    case_from_mapping,
    case_from_path,
    load_spec,
    require_closed,
)
from src.eval.store import assert_outside_spec_namespace
from src.eval.types import Bounds, Probe, QueryRequest
from src.eval.verdict import reject_combined_average
from tests.eval_ports import DictCache, FixedMetrics, ScriptedModel

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "eval"
SPEC_CLOSED = FIXTURES / "spec_closed"
SPEC_BATCH = FIXTURES / "spec_batch"
SPEC_UNEQUAL = FIXTURES / "spec_unequal"
SPEC_REALLOC = FIXTURES / "spec_realloc"
SPEC_UNRESOLVED = FIXTURES / "spec_unresolved"
SPEC_PROFILE_A = FIXTURES / "spec_profile_a"
REAL_SPEC = ROOT / ".factverify" / "spec"
SRC_EVAL = ROOT / "src" / "eval"


def _request(
    kind: str,
    *,
    prompts: int = 1,
    samples: int = 1,
    spend: bool = False,
) -> QueryRequest:
    return QueryRequest(
        channel_id="prompt_variation",
        kind=kind,
        probe_id="probe_native",
        prompt_count=prompts,
        sample_count=samples,
        spend_confirmation=spend,
    )


def _accountant(spec: Path, arm: str = "native") -> Accountant:
    return Accountant(load_spec(spec), arm)


def _bounds(split: str, **values: float) -> Bounds:
    base = {
        "rouge_l": 1.0,
        "bertscore": 1.0,
        "truth_ratio": 1.0,
        "answer_probability": 1.0,
        "answer_rank": 1.0,
        "prompt_variation": 1.0,
    }
    base.update(values)
    return Bounds(split=split, by_channel=base)


def test_fv_eval_001_all_calls_charged() -> None:
    accountant = _accountant(SPEC_BATCH)
    result = accountant.query(
        "prompt_variation", _request("generation", prompts=2, samples=3)
    )
    assert result.generation_trials == 6
    assert accountant.channel_remaining("prompt_variation") == 0
    hits = illegal_calls_in_source("model.generate()\n", "native.py")
    assert hits == [("native.py", 1)]
    assert illegal_model_calls(SRC_EVAL) == []


def test_fv_eval_002_refuses_overspend() -> None:
    accountant = _accountant(SPEC_CLOSED)
    result = accountant.query(
        "prompt_variation", _request("generation", prompts=2, samples=1)
    )
    assert result.remaining == 0
    with pytest.raises(BudgetExhaustedError) as caught:
        accountant.query("prompt_variation", _request("generation"))
    assert caught.value.remaining == 0
    record = accountant.budget_record()
    assert record.channels[0].remaining == 0 or any(
        item.channel_id == "prompt_variation" and item.remaining == 0
        for item in record.channels
    )
    assert len(record.refused_requests) == 1


def test_fv_eval_003_equal_totals() -> None:
    assert start_run(load_spec(SPEC_CLOSED)) == 4
    with pytest.raises(FactVerifyEvalError, match="factverify=5") as caught:
        start_run(load_spec(SPEC_UNEQUAL))
    message = str(caught.value)
    assert "native=4" in message
    assert "semantic_only=4" in message
    with pytest.raises(FactVerifyEvalError, match="D-22"):
        require_closed(load_spec(REAL_SPEC), ["D-22"])


def test_fv_eval_004_cost_vector() -> None:
    accountant = _accountant(SPEC_CLOSED)
    accountant.query("prompt_variation", _request("generation"))
    record = accountant.budget_record()
    for name in (
        "generated_trials",
        "scored_candidates",
        "input_tokens",
        "output_tokens",
        "tokens",
        "exports",
        "training_steps",
        "wall_clock_seconds",
        "gpu_hours",
        "peak_memory_bytes",
        "permitted_vs_actual",
        "confirmation_remaining",
    ):
        assert getattr(record, name) is not None
    prompt = next(
        item for item in record.channels if item.channel_id == "prompt_variation"
    )
    assert prompt.remaining == prompt.permitted - prompt.charged_observations
    assert prompt.remaining == 1


def test_fv_eval_005_confirmation_reserve() -> None:
    blocked = _accountant(SPEC_CLOSED)
    charged = blocked.query(
        "confirmation",
        QueryRequest("confirmation", "generation", "p", prompt_count=1, sample_count=1),
    )
    assert charged.remaining == 0
    with pytest.raises(BudgetExhaustedError):
        blocked.query(
            "confirmation",
            QueryRequest(
                "confirmation", "generation", "p2", prompt_count=1, sample_count=1
            ),
        )
    fresh = _accountant(SPEC_CLOSED)
    with pytest.raises(FactVerifyEvalError, match="confirmation"):
        fresh.query("prompt_variation", _request("generation", spend=True))
    assert fresh.channel_remaining("confirmation") == 1
    allowed = _accountant(SPEC_REALLOC)
    allowed.query("prompt_variation", _request("generation", spend=True))
    assert allowed.channel_remaining("confirmation") == 0
    assert allowed.channel_remaining("prompt_variation") == 2


def test_fv_eval_006_cache_retry_policy() -> None:
    accountant = _accountant(SPEC_CLOSED)
    hit = accountant.query("prompt_variation", _request("cache_hit"))
    assert hit.generation_trials == 0
    assert hit.new_compute_trials == 0
    assert accountant.channel_remaining("prompt_variation") == 1
    retry = _accountant(SPEC_CLOSED)
    retried = retry.query("prompt_variation", _request("retry"))
    assert retried.new_compute_trials == 2
    assert retry.channel_remaining("prompt_variation") == 0
    failed = _accountant(SPEC_CLOSED)
    failure = failed.query("prompt_variation", _request("transport_failure"))
    assert failure.generation_trials == 0
    assert failure.new_compute_trials == 1
    assert failed.channel_remaining("prompt_variation") == 2
    with pytest.raises(FactVerifyEvalError, match="cache_policy.charge_rule"):
        start_run(load_spec(SPEC_UNRESOLVED))


def test_fv_eval_007_access_gate() -> None:
    bundle = load_spec(SPEC_PROFILE_A)
    permit(bundle, "prompt_variation", "generation")
    with pytest.raises(FactVerifyEvalError, match="raw_likelihood"):
        permit(bundle, "raw_likelihood", "candidate_score")


def test_fv_eval_008_native_probes() -> None:
    case = case_from_path(FIXTURES / "cases" / "calibration.json")
    native = next(probe for probe in case.probes if probe.probe_class == "native")
    template = next(probe for probe in case.probes if probe.template_id == "tmpl_cal")
    bundle = load_spec(SPEC_CLOSED)
    gateway = _gateway(bundle)
    scores = score_native(
        bundle,
        case,
        native,
        gateway,
        FixedMetrics(),
        _bounds("calibration").by_channel,
    )
    assert {item.channel_id for item in scores} == {
        "rouge_l",
        "bertscore",
        "truth_ratio",
        "answer_probability",
        "answer_rank",
    }
    with pytest.raises(FactVerifyEvalError, match="tmpl_cal"):
        score_native(
            bundle,
            case,
            template,
            _gateway(bundle),
            FixedMetrics(),
            _bounds("calibration").by_channel,
        )
    text_only = load_spec(SPEC_PROFILE_A)
    limited = score_native(
        text_only,
        case,
        native,
        _gateway(text_only),
        FixedMetrics(),
        _bounds("calibration").by_channel,
    )
    assert {item.channel_id for item in limited} == {"rouge_l", "bertscore"}
    assert all(item.score != 0 or item.channel_id == "rouge_l" for item in limited)


def test_fv_eval_009_split_templates() -> None:
    bundle = load_spec(SPEC_CLOSED)
    final_case = case_from_path(FIXTURES / "cases" / "final_test_probe.json")
    primary, _inference = select_equivalence(bundle, final_case, final_case.probes)
    assert [probe.template_id for probe in primary] == ["tmpl_final"]
    wrong = Probe(
        "probe_cal",
        "template",
        "Zephyr?",
        template_id="tmpl_cal",
        group_id="grp_cal",
    )
    with pytest.raises(FactVerifyEvalError, match="grp_cal") as caught:
        select_equivalence(bundle, final_case, [wrong])
    assert "calibration" in str(caught.value)
    assert "final_test" in str(caught.value)
    inferred = case_from_path(FIXTURES / "cases" / "inference.json")
    _primary, inference = select_equivalence(bundle, inferred, inferred.probes)
    assert [probe.template_id for probe in inference] == ["tmpl_infer"]
    with pytest.raises(FactVerifyEvalError, match="inference_output") as drawn:
        require_primary(bundle, inferred, inferred.probes[0])
    assert "tmpl_infer" in str(drawn.value)


def test_fv_eval_010_verdict_vocabulary(tmp_path: Path) -> None:
    case = case_from_path(FIXTURES / "cases" / "calibration.json")
    result = evaluate_case(
        case,
        spec_root=SPEC_CLOSED,
        raw_dir=tmp_path / "raw",
        model=ScriptedModel(),
        cache=DictCache(),
        metrics=FixedMetrics(),
        arm="native",
        bounds=_bounds("calibration"),
    )
    verdict = result.verdicts[0]
    assert verdict.status == "conformant under the declared test"
    assert verdict.status_code == "conformance"
    assert verdict.access_label == "A"
    assert verdict.checkpoint_ledger_id == "led-1"
    assert verdict.fact_id == "fact-1"
    assert verdict.split == "calibration"
    assert verdict.arm_id == "native"
    assert verdict.spec_revision == "fixture-eval"
    hidden = case_from_mapping(
        {
            **json.loads((FIXTURES / "cases" / "calibration.json").read_text()),
            "identifiability": "structurally_indistinguishable",
        }
    )
    blocked = evaluate_case(
        hidden,
        spec_root=SPEC_CLOSED,
        raw_dir=tmp_path / "raw-hidden",
        model=ScriptedModel(fail=True),
        cache=DictCache(),
        metrics=FixedMetrics(),
        arm="native",
        bounds=_bounds("calibration"),
    )
    assert blocked.verdicts[0].status == "non-identifiable under this profile"
    payload = json.loads((FIXTURES / "cases" / "calibration.json").read_text())
    del payload["identifiability"]
    with pytest.raises(FactVerifyEvalError, match="identifiability"):
        case_from_mapping(payload)


def test_fv_eval_011_decision_rule(tmp_path: Path) -> None:
    lone = _semantic_case("lone", ["direct"])
    low = _bounds("calibration", prompt_variation=0.0)
    one = evaluate_case(
        lone,
        spec_root=SPEC_CLOSED,
        raw_dir=tmp_path / "one",
        model=ScriptedModel(),
        cache=DictCache(),
        metrics=FixedMetrics(),
        arm="semantic_only",
        bounds=low,
    )
    assert one.verdicts[0].status != "confirmed recovery witness"
    assert one.verdicts[0].diagnostics.raw_maximum == 1.0
    pair = _semantic_case("pair", ["direct", "inverse"])
    two = evaluate_case(
        pair,
        spec_root=SPEC_CLOSED,
        raw_dir=tmp_path / "two",
        model=ScriptedModel(),
        cache=DictCache(),
        metrics=FixedMetrics(),
        arm="semantic_only",
        bounds=low,
    )
    assert two.verdicts[0].status == "confirmed recovery witness"
    assert two.verdicts[0].confirmation_route == "A"
    bundle = load_spec(SPEC_CLOSED)
    bundle.raw_maximum_role = "verdict"
    from src.eval.factverify import decide

    with pytest.raises(FactVerifyEvalError, match="raw_maximum_role"):
        decide(bundle, lone, "semantic_only", [], None)


def test_fv_eval_012_frozen_thresholds(tmp_path: Path) -> None:
    digest_file = tmp_path / "results" / "thresholds.json"
    digest_file.parent.mkdir()
    digest_file.write_text(
        json.dumps({"bounds": {"prompt_variation": 1.0, "rouge_l": 1.0}})
    )
    digest = hashlib.sha256(digest_file.read_bytes()).hexdigest()

    class Source:
        def __init__(self, exists: bool, blob: str | None) -> None:
            self._exists = exists
            self._blob = blob

        def tag_exists(self, tag: str) -> bool:
            assert tag == "thresholds-v1"
            return self._exists

        def blob_sha256(self, tag: str, path: str) -> str | None:
            assert tag == "thresholds-v1"
            assert path == "results/thresholds.json"
            return self._blob

    case = case_from_path(FIXTURES / "cases" / "final_test_probe.json")
    finished = evaluate_case(
        case,
        spec_root=SPEC_CLOSED,
        raw_dir=tmp_path / "raw",
        model=ScriptedModel(),
        cache=DictCache(),
        metrics=FixedMetrics(),
        arm="semantic_only",
        thresholds_path=digest_file,
        thresholds_source=Source(True, digest),
    )
    assert finished.verdicts[0].thresholds_tag == "thresholds-v1"
    with pytest.raises(FactVerifyEvalError, match="thresholds-v1"):
        evaluate_case(
            case,
            spec_root=SPEC_CLOSED,
            raw_dir=tmp_path / "missing-tag",
            model=ScriptedModel(),
            cache=DictCache(),
            metrics=FixedMetrics(),
            arm="semantic_only",
            thresholds_path=digest_file,
            thresholds_source=Source(False, digest),
        )
    with pytest.raises(FactVerifyEvalError, match="thresholds-v1"):
        evaluate_case(
            case,
            spec_root=SPEC_CLOSED,
            raw_dir=tmp_path / "bad-digest",
            model=ScriptedModel(),
            cache=DictCache(),
            metrics=FixedMetrics(),
            arm="semantic_only",
            thresholds_path=digest_file,
            thresholds_source=Source(True, "0" * 64),
        )
    with pytest.raises(FactVerifyEvalError, match="bounds"):
        evaluate_case(
            case,
            spec_root=SPEC_CLOSED,
            raw_dir=tmp_path / "arg-bounds",
            model=ScriptedModel(),
            cache=DictCache(),
            metrics=FixedMetrics(),
            arm="semantic_only",
            bounds=_bounds("final_test"),
            thresholds_path=digest_file,
            thresholds_source=Source(True, digest),
        )
    calibration = case_from_path(FIXTURES / "cases" / "calibration.json")
    with pytest.raises(FactVerifyEvalError, match="bounds split"):
        evaluate_case(
            calibration,
            spec_root=SPEC_CLOSED,
            raw_dir=tmp_path / "cal",
            model=ScriptedModel(),
            cache=DictCache(),
            metrics=FixedMetrics(),
            arm="native",
            bounds=_bounds("final_test"),
        )


def test_fv_eval_013_no_channel_average(tmp_path: Path) -> None:
    result = evaluate_case(
        case_from_path(FIXTURES / "cases" / "calibration.json"),
        spec_root=SPEC_CLOSED,
        raw_dir=tmp_path / "raw",
        model=ScriptedModel(),
        cache=DictCache(),
        metrics=FixedMetrics(),
        arm="native",
        bounds=_bounds("calibration"),
    )
    payload = result.verdicts[0]
    assert payload.scores
    assert all(
        hasattr(item, "channel_id") and hasattr(item, "bound")
        for item in payload.scores
    )
    for banned in ("average", "combined_score", "mean_score"):
        assert not hasattr(payload, banned)
    with pytest.raises(FactVerifyEvalError, match="average"):
        reject_combined_average({"average": 0.5})


def test_fv_eval_014_raw_generations(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw"
    case = case_from_path(FIXTURES / "cases" / "calibration.json")
    first = evaluate_case(
        case,
        spec_root=SPEC_CLOSED,
        raw_dir=raw_dir,
        model=ScriptedModel(),
        cache=DictCache(),
        metrics=FixedMetrics(),
        arm="native",
        bounds=_bounds("calibration"),
    )
    record = first.budget_records[0]
    from src.eval.store import RawStore

    store = RawStore(raw_dir)
    assert store.count(case.case_id, "native") == record.generated_trials
    line = store.read(case.case_id, "native")[0]
    for key in (
        "case_id",
        "checkpoint_ledger_id",
        "fact_id",
        "split",
        "arm_id",
        "channel_id",
        "probe_id",
        "prompt",
        "completion",
        "decoding",
        "seed",
    ):
        assert key in line
    with pytest.raises(FactVerifyEvalError, match="factverify"):
        assert_outside_spec_namespace(ROOT / ".factverify" / "raw-out")
    second = evaluate_case(
        case,
        spec_root=SPEC_CLOSED,
        raw_dir=raw_dir,
        model=ScriptedModel(fail=True),
        cache=DictCache(),
        metrics=FixedMetrics(),
        arm="native",
        bounds=_bounds("calibration"),
        replay=True,
    )
    assert second.verdicts[0].status == first.verdicts[0].status
    assert [(item.channel_id, item.score) for item in second.verdicts[0].scores] == [
        (item.channel_id, item.score) for item in first.verdicts[0].scores
    ]


def _gateway(bundle: object) -> object:
    from src.eval.gateway import Gateway
    from src.eval.spec_load import SpecBundle

    assert isinstance(bundle, SpecBundle)
    return Gateway(
        Accountant(bundle, "native"),
        ScriptedModel(),
        DictCache(),
        identity_hash="fixture",
    )


def _semantic_case(case_id: str, families: list[str]) -> object:
    from src.eval.types import Case

    probes = [
        Probe(
            probe_id=f"p-{family}",
            probe_class="template",
            prompt="Where is Zephyr?",
            template_id="tmpl_cal",
            group_id="grp_cal",
            family_id=family,
        )
        for family in families
    ]
    return Case(
        case_id=case_id,
        checkpoint_ledger_id="led-1",
        fact_id="fact-1",
        split="calibration",
        spec_revision="fixture-eval",
        access_label="A",
        identifiability="identifiable",
        answers=["Zephyr"],
        probes=probes,
    )
