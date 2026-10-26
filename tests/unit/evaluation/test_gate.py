"""Tests for Gate 1 analysis."""

from __future__ import annotations

from src.services.evaluation.gate import analyze_gate1


class TestAnalyzeGate1:
    def test_no_data(self) -> None:
        report = analyze_gate1("job1", "f1", {}, {})
        assert report.decision == "NO_DATA"
        assert report.total_facts == 0

    def test_pass_clear_forget_signal(self) -> None:
        """Forgetter has much lower answer_probability on forget fact → PASS."""
        forgetter = {
            "f1": {"rouge_l": 0.1, "truth_ratio": 0.1, "answer_probability": 0.01, "answer_rank": 50.0},
            "f2": {"rouge_l": 0.8, "truth_ratio": 0.9, "answer_probability": 0.8, "answer_rank": 1.5},
        }
        referencer = {
            "f1": {"rouge_l": 0.9, "truth_ratio": 0.8, "answer_probability": 0.85, "answer_rank": 1.0},
            "f2": {"rouge_l": 0.8, "truth_ratio": 0.9, "answer_probability": 0.8, "answer_rank": 1.5},
        }
        report = analyze_gate1("job1", "f1", forgetter, referencer)
        assert report.decision == "PASS"
        assert report.total_facts == 2
        assert report.retain_count == 1
        # Forget delta: answer_probability should be negative (forgetter lower)
        assert report.forget_delta["answer_probability"] < -0.05

    def test_fail_no_forget_signal(self) -> None:
        """Forgetter and referencer similar on forget fact → FAIL."""
        forgetter = {
            "f1": {"rouge_l": 0.8, "truth_ratio": 0.8, "answer_probability": 0.8, "answer_rank": 1.5},
        }
        referencer = {
            "f1": {"rouge_l": 0.8, "truth_ratio": 0.8, "answer_probability": 0.8, "answer_rank": 1.5},
        }
        report = analyze_gate1("job1", "f1", forgetter, referencer)
        assert report.decision == "FAIL"

    def test_retain_delta_computed(self) -> None:
        """Retain facts have small deltas."""
        forgetter = {
            "f1": {"rouge_l": 0.0, "truth_ratio": 0.0, "answer_probability": 0.0, "answer_rank": 100.0},
            "r1": {"rouge_l": 0.8, "truth_ratio": 0.9, "answer_probability": 0.8, "answer_rank": 1.5},
            "r2": {"rouge_l": 0.7, "truth_ratio": 0.8, "answer_probability": 0.7, "answer_rank": 2.0},
        }
        referencer = {
            "f1": {"rouge_l": 0.9, "truth_ratio": 0.8, "answer_probability": 0.85, "answer_rank": 1.0},
            "r1": {"rouge_l": 0.8, "truth_ratio": 0.9, "answer_probability": 0.8, "answer_rank": 1.5},
            "r2": {"rouge_l": 0.7, "truth_ratio": 0.8, "answer_probability": 0.7, "answer_rank": 2.0},
        }
        report = analyze_gate1("job1", "f1", forgetter, referencer)
        # Retain deltas should be 0 or near 0
        assert report.retain_delta["rouge_l"] == 0.0
        assert report.retain_delta["answer_probability"] == 0.0

    def test_comparisons_list(self) -> None:
        """Report includes per-fact comparisons."""
        forgetter = {
            "f1": {"rouge_l": 0.1, "truth_ratio": 0.1, "answer_probability": 0.01, "answer_rank": 50.0},
        }
        referencer = {
            "f1": {"rouge_l": 0.9, "truth_ratio": 0.8, "answer_probability": 0.85, "answer_rank": 1.0},
        }
        report = analyze_gate1("job1", "f1", forgetter, referencer)
        assert len(report.comparisons) == 1
        assert report.comparisons[0].fact_id == "f1"
        assert report.comparisons[0].is_forget is True

    def test_forget_fact_not_in_common(self) -> None:
        """When forget fact is not evaluated, report UNDETERMINED."""
        forgetter = {"r1": {"rouge_l": 0.8, "truth_ratio": 0.8, "answer_probability": 0.8, "answer_rank": 1.5}}
        referencer = {"r1": {"rouge_l": 0.8, "truth_ratio": 0.8, "answer_probability": 0.8, "answer_rank": 1.5}}
        report = analyze_gate1("job1", "f1", forgetter, referencer)
        assert report.decision == "UNDETERMINED"
