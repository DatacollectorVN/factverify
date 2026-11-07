"""Shared token batching and causal-LM loss for the named trainers."""

from __future__ import annotations

from typing import Any, Literal

import torch

from src.services.data.qa_format import answer_start_index, eos_text, qa_prompt, qa_text
from src.train.config import JobConfig
from src.train.data import DataCatalog

_SELECTION_ATTR = "_fv_selection"
_STOP_ATTR = "_fv_stop"

#: Why a training loop ended.
STOP_REASONS = ("early_stop", "neighbour_guard", "max_epochs")
ScoreMode = Literal["min", "max"]


def prepare_batch(
    tokenizer: Any, text: str, max_length: int
) -> dict[str, torch.Tensor]:
    """Tokenize one item. Padding positions are masked in the labels."""
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    encoded = tokenizer(
        text,
        truncation=True,
        max_length=max_length,
        padding="max_length",
        return_tensors="pt",
    )
    input_ids = encoded["input_ids"]
    attention_mask = encoded["attention_mask"]
    labels = input_ids.clone()
    labels[attention_mask == 0] = -100
    return {
        "input_ids": input_ids,
        "attention_mask": attention_mask,
        "labels": labels,
    }


def prepare_qa_batch(
    tokenizer: Any, question: str, answer: str, max_length: int
) -> dict[str, torch.Tensor]:
    """Tokenize a QA pair, masking question tokens in labels.

    The model sees the full sequence (question + answer) but the loss is
    computed only on the answer tokens. This trains the model to produce the
    right answer given the question, without wasting gradient on memorizing
    question phrasings.
    """
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    prompt = qa_prompt(question)
    answer_text = qa_text(question, answer)
    # First answer token index (boundary before the space; see qa_format)
    prompt_len = answer_start_index(tokenizer, prompt, answer_text)
    # The trained answer ends with <EOS> so the model learns where to stop
    full_text = answer_text + eos_text(tokenizer) if answer else answer_text
    encoded = tokenizer(
        full_text,
        truncation=True,
        max_length=max_length,
        padding="max_length",
        return_tensors="pt",
    )
    input_ids = encoded["input_ids"]
    attention_mask = encoded["attention_mask"]
    labels = input_ids.clone()
    # Mask padding
    labels[attention_mask == 0] = -100
    # Mask question/prompt tokens — only train on answer
    seq_len = int(attention_mask.sum())
    # Clamp prompt_len so at least 1 answer token is trained on
    effective_prompt_len = min(prompt_len, seq_len - 1)
    labels[0, :effective_prompt_len] = -100
    return {
        "input_ids": input_ids,
        "attention_mask": attention_mask,
        "labels": labels,
    }


def causal_nll(model: Any, batch: dict[str, torch.Tensor]) -> torch.Tensor:
    """Mean token cross-entropy. The batch is moved onto the model device."""
    device = next(model.parameters()).device
    moved = {key: value.to(device) for key, value in batch.items()}
    return model(
        input_ids=moved["input_ids"],
        attention_mask=moved["attention_mask"],
        labels=moved["labels"],
    ).loss


def read_ordered(catalog: DataCatalog, order: list[str]) -> dict[str, str]:
    """Read each id once, in `order`, through the catalog."""
    return {item_id: catalog.get(item_id) for item_id in order}


def adamw(model: Any, config: JobConfig) -> torch.optim.Optimizer:
    """AdamW over trainable parameters. Coefficients come only from the job."""
    parameters = [param for param in model.parameters() if param.requires_grad]
    return torch.optim.AdamW(
        parameters,
        lr=config.learning_rate,
        weight_decay=config.weight_decay,
    )


class BestEpochTracker:
    """Keep the best epoch weights and count epochs without a better score.

    `patience is None` leaves training unchanged: updates do not store weights
    and never request a stop. When patience is set, the first epoch is the
    initial best. A later epoch improves only on a strictly better score
    (`min` lower, `max` higher). Training should stop once `patience`
    non-improving epochs have followed the best one.
    """

    def __init__(
        self, mode: ScoreMode, patience: int | None, min_delta: float = 0.0
    ) -> None:
        if mode not in ("min", "max"):
            raise ValueError(f"unknown score mode {mode!r}")
        if min_delta < 0:
            raise ValueError(f"min_delta must be >= 0, got {min_delta}")
        self.mode: ScoreMode = mode
        self.patience = patience
        #: An epoch counts as an improvement only if it beats the best score
        #: by more than this margin (0.0 = any strictly better score).
        self.min_delta = float(min_delta)
        self.best_score: float | None = None
        self.best_epoch: int | None = None
        self.stopped_epoch: int | None = None
        self.wait = 0
        self._best_state: dict[str, torch.Tensor] | None = None

    def update(self, epoch: int, score: float, model: Any) -> bool:
        """Record one finished epoch. Return True when patience is exhausted."""
        if self.patience is None:
            return False
        improved = self.best_score is None or (
            score < self.best_score - self.min_delta
            if self.mode == "min"
            else score > self.best_score + self.min_delta
        )
        if improved:
            self.best_score = float(score)
            self.best_epoch = epoch
            self.wait = 0
            self._best_state = {
                key: tensor.detach().cpu().clone()
                for key, tensor in model.state_dict().items()
            }
        else:
            self.wait += 1
        self.stopped_epoch = epoch
        return self.wait >= self.patience

    def status(self) -> str:
        """Epoch-log suffix, empty when early stopping is off."""
        if self.patience is None or self.best_score is None or self.best_epoch is None:
            return ""
        return (
            f"  best={self.best_score:.4f}@epoch{self.best_epoch}"
            f"  wait={self.wait}/{self.patience}"
        )

    def restore(self, model: Any) -> None:
        """Load the best weights back into `model`. No-op without a snapshot."""
        if self._best_state is None:
            return
        model.load_state_dict(self._best_state)

    def remember(self, model: Any) -> None:
        """Stash the selection summary on `model` for checkpoint metadata."""
        if (
            self.best_epoch is None
            or self.best_score is None
            or self.stopped_epoch is None
        ):
            return
        setattr(
            model,
            _SELECTION_ATTR,
            {
                "best_epoch": self.best_epoch,
                "best_score": self.best_score,
                "stopped_epoch": self.stopped_epoch,
            },
        )

    def state_dict(self) -> dict[str, Any]:
        """Serialise tracker state for resume checkpoints."""
        return {
            "mode": self.mode,
            "patience": self.patience,
            "min_delta": self.min_delta,
            "best_score": self.best_score,
            "best_epoch": self.best_epoch,
            "stopped_epoch": self.stopped_epoch,
            "wait": self.wait,
            "_best_state": self._best_state,
        }

    @classmethod
    def from_state_dict(cls, state: dict[str, Any]) -> "BestEpochTracker":
        """Reconstruct a tracker from a serialised state dict."""
        tracker = cls(
            mode=state["mode"],
            patience=state["patience"],
            min_delta=float(state.get("min_delta", 0.0)),
        )
        tracker.best_score = state["best_score"]
        tracker.best_epoch = state["best_epoch"]
        tracker.stopped_epoch = state["stopped_epoch"]
        tracker.wait = state["wait"]
        tracker._best_state = state["_best_state"]
        return tracker


def selection_summary(model: Any) -> dict[str, Any] | None:
    """Return the best-epoch summary stored by BestEpochTracker.remember."""
    value = getattr(model, _SELECTION_ATTR, None)
    if not isinstance(value, dict):
        return None
    return value


def remember_stop(
    model: Any, *, reason: str, stopped_epoch: int, has_selected_checkpoint: bool
) -> None:
    """Stash why training ended and whether a valid selected checkpoint exists.

    ``has_selected_checkpoint`` is False when the neighbour guard tripped
    before any non-breaching epoch was recorded: the weights in ``model`` are
    then the breached ones and must not be reported as a selected checkpoint.
    """
    if reason not in STOP_REASONS:
        raise ValueError(f"unknown stop reason {reason!r}")
    setattr(
        model,
        _STOP_ATTR,
        {
            "stop_reason": reason,
            "stopped_epoch": stopped_epoch,
            "has_selected_checkpoint": has_selected_checkpoint,
        },
    )


def stop_summary(model: Any) -> dict[str, Any] | None:
    """Return the stop summary stored by :func:`remember_stop`."""
    value = getattr(model, _STOP_ATTR, None)
    if not isinstance(value, dict):
        return None
    return value


def tracker_min_delta(config: Any) -> float:
    """``training.min_delta`` (default 0.0 = any strictly better score)."""
    raw = getattr(config, "raw", None)
    training = raw.get("training", {}) if isinstance(raw, dict) else {}
    return float(training.get("min_delta", 0.0))
