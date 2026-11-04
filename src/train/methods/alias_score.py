"""Alias-aware scoring and loss utilities.

Replaces single-string log-probability measurement with logsumexp over all
valid aliases of an answer entity.  One operation applied consistently to
probe scoring, learning loss, and unlearning loss.

Core principle:
    Single-string:  log P("Santiago city" | q)
    Alias-aware:    logsumexp(log P(alias_i | q) for alias_i in aliases)
                  = log[P("Santiago" | q) + P("Santiago city" | q) + ...]

The alias-aware value is always ≥ the single-string value.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import TYPE_CHECKING, Any

import torch
import torch.nn.functional as F

if TYPE_CHECKING:
    from src.train.data import EvalProbe
    from src.train.data import DataCatalog

#: Boolean alias sets for the ``verify`` family.
#: Stored here (not in a spec file) because the values are surface forms of
#: logical constants, not empirical choices — they cannot be tuned on data.
BOOLEAN_ALIASES: dict[str, list[str]] = {
    "positive": ["True", "Yes", "Correct", "true", "yes"],
    "negative": ["False", "No", "Incorrect", "false", "no"],
}


class EntityAliasStore:
    """Loads and caches entity alias lists from a directory of JSON files.

    Each JSON file has the form ``{entity_name}.json`` where the entity name
    is the last colon-separated segment of the entity ID
    (``"factverify:entity:santiago_chile"`` → ``"santiago_chile.json"``).

    Args:
        entities_dir: Path to the directory containing entity JSON files.
                      Typically ``<corpus_dir>/../entities/``.
    """

    def __init__(self, entities_dir: Path) -> None:
        self._entities_dir = entities_dir
        # Cache: (entity_name, language) -> list[str]
        self._cache: dict[tuple[str, str], list[str]] = {}

    def get_aliases(self, entity_id: str, language: str = "en") -> list[str]:
        """Return alias values for *entity_id* filtered to *language*.

        Args:
            entity_id: Full factverify entity ID such as
                ``"factverify:entity:santiago_chile"``.
            language: BCP-47 language tag (e.g. ``"en"``, ``"vi"``).

        Returns:
            List of alias strings, possibly empty.  Never raises.
        """
        if not entity_id:
            return []
        entity_name = entity_id.split(":")[-1]
        key = (entity_name, language)
        if key not in self._cache:
            self._cache[key] = self._load(entity_name, language)
        return self._cache[key]

    def _load(self, entity_name: str, language: str) -> list[str]:
        path = self._entities_dir / f"{entity_name}.json"
        if not path.is_file():
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return []
        return [
            str(a["value"])
            for a in data.get("alias", [])
            if a.get("language") == language
        ]


def get_probe_aliases(
    probe: "EvalProbe",
    alias_store: EntityAliasStore | None,
    *,
    fallback_to_answer: bool = True,
) -> list[str]:
    """Resolve the alias set for one probe.

    Resolution rules (applied in order):

    1. ``verify`` family: returns :data:`BOOLEAN_ALIASES` ``["positive"]`` or
       ``["negative"]`` depending on ``probe.answer.lower()``.
    2. Other families with a non-empty ``probe.answer_entity_id`` and a
       non-``None`` ``alias_store``: queries the store for language-filtered
       entity aliases.  Returns the alias list if non-empty.
    3. Fallback: ``[probe.answer]`` when ``fallback_to_answer=True`` (default).
       This preserves single-string behaviour exactly when no alias expansion
       is possible.

    Args:
        probe:              The probe to resolve aliases for.
        alias_store:        Entity alias store.  ``None`` → always fallback.
        fallback_to_answer: When ``True`` (default), return ``[probe.answer]``
                            as a last resort so callers always get a non-empty
                            list.
    """
    if probe.family == "verify":
        answer_lower = probe.answer.lower().strip()
        if answer_lower in {"true", "yes", "correct"}:
            return BOOLEAN_ALIASES["positive"]
        return BOOLEAN_ALIASES["negative"]

    if alias_store is not None and probe.answer_entity_id:
        aliases = alias_store.get_aliases(probe.answer_entity_id, probe.language)
        if aliases:
            return aliases

    if fallback_to_answer:
        return [probe.answer]
    return []


def score_answer_aliases(
    model: Any,
    tokenizer: Any,
    question: str,
    aliases: list[str],
) -> float:
    """Return logsumexp of sequence log probs across all aliases (no grad).

    Calls :func:`_score_answer_full` once per alias, collects the
    ``sequence_log_probability`` values, and applies ``torch.logsumexp``.

    When *aliases* is empty, returns ``0.0`` (matches the convention of
    :func:`_score_answer_full` for zero-token answers).

    When *aliases* has exactly one element, the logsumexp is a no-op and the
    result equals the single-string sequence log probability.

    The caller is responsible for the ``model.eval()`` context.
    """
    from src.train.methods.fact_score import _score_answer_full  # local to avoid circular

    if not aliases:
        return 0.0

    slps: list[float] = []
    for alias in aliases:
        _, _, _, slp = _score_answer_full(model, tokenizer, question, alias)
        slps.append(slp)

    if len(slps) == 1:
        return slps[0]

    t = torch.tensor(slps, dtype=torch.float64)
    return float(torch.logsumexp(t, dim=0).item())


def alias_log_prob(
    model: Any,
    tokenizer: Any,
    question: str,
    aliases: list[str],
    max_length: int,
) -> torch.Tensor:
    """Return logsumexp of sequence log probs as a differentiable tensor.

    For each alias one forward pass is performed:

    1. Build ``full_text = "Q: {question}\\nA: {alias}"``.
    2. Run the model; extract answer-token logits at positions
       ``[prompt_len-1 : -1]``.
    3. Apply ``log_softmax``; gather gold-token log probs; sum them.

    The per-alias scalar tensors are stacked and ``torch.logsumexp`` is
    applied.

    **Sign convention**: the return value is ``logsumexp(log P(alias_i|q))``
    which is always ≤ 0 (a log probability).

    - For *learning*: ``loss = -alias_log_prob(...)`` (descent maximises prob).
    - For *forgetting* (GA-style): ``loss = alias_log_prob(...)`` (descent
      minimises log prob).

    The caller must NOT wrap this in ``torch.no_grad()`` — the computation
    graph must be intact for ``.backward()`` to work.  The caller is also
    responsible for switching the model in/out of ``eval()`` mode if needed
    (see individual method modules).

    When *aliases* is empty, returns a zero tensor with no grad contribution.
    When *aliases* has a single element, skips the logsumexp for efficiency.
    """
    if not aliases:
        device = next(model.parameters()).device
        return torch.zeros(1, device=device, requires_grad=False).squeeze()

    device = next(model.parameters()).device
    qa_prompt = f"Q: {question}\nA: "
    prompt_ids = tokenizer(qa_prompt, return_tensors="pt")["input_ids"]
    prompt_len = int(prompt_ids.shape[1])

    per_alias: list[torch.Tensor] = []
    for alias in aliases:
        full_text = qa_prompt + alias
        full_ids = tokenizer(full_text, return_tensors="pt")["input_ids"].to(device)
        if int(full_ids.shape[1]) <= prompt_len:
            # Zero-token alias — treat as -∞ (contribute nothing to logsumexp)
            per_alias.append(torch.tensor(float("-inf"), device=device))
            continue
        logits = model(input_ids=full_ids).logits  # (1, seq_len, vocab)
        answer_logits = logits[0, prompt_len - 1 : -1]  # (n_answer_tokens, vocab)
        answer_ids = full_ids[0, prompt_len:]           # (n_answer_tokens,)
        log_p = F.log_softmax(answer_logits, dim=-1)
        n_tokens = int(answer_ids.shape[0])
        token_lp = log_p[range(n_tokens), answer_ids]
        per_alias.append(token_lp.sum())

    if len(per_alias) == 1:
        return per_alias[0]

    return torch.logsumexp(torch.stack(per_alias), dim=0)


def compute_entropy_loss(
    model: Any,
    tokenizer: Any,
    question: str,
    max_length: int,
    *,
    entropy_target_nats: float,
) -> torch.Tensor:
    """Entropy floor loss: ``relu(H_target − H(P_model(·|q)))``.

    Computes Shannon entropy of the first-answer-token output distribution.
    Returns zero (no gradient) when the model is already uncertain enough
    (H ≥ H_target).  Returns a positive tensor that pushes the model toward
    higher entropy when H < H_target.

    Args:
        model:                The model (gradients must be enabled).
        tokenizer:            The tokenizer.
        question:             Question text (without ``"Q: "`` prefix).
        max_length:           Max sequence length (not currently used for
                              truncation but kept for API consistency).
        entropy_target_nats:  H_target in nats.  Convert from bits:
                              ``bits * math.log(2)``.
    """
    device = next(model.parameters()).device
    qa_prompt = f"Q: {question}\nA: "
    input_ids = tokenizer(qa_prompt, return_tensors="pt")["input_ids"].to(device)
    prompt_len = int(input_ids.shape[1])
    logits = model(input_ids=input_ids).logits  # (1, seq_len, vocab)
    # First answer-token position
    first_logits = logits[0, prompt_len - 1]    # (vocab,)
    log_p = F.log_softmax(first_logits, dim=-1)
    p = log_p.exp()
    # H = -sum(p * log_p); clamp log_p to avoid 0 * -inf = nan
    H = -(p * log_p.clamp(min=-1e9)).sum()
    return F.relu(torch.tensor(entropy_target_nats, device=device, dtype=H.dtype) - H)


# ── Helpers used by training method modules ──────────────────────────────────

def alias_store_from_config(config: Any) -> EntityAliasStore | None:
    """Construct an :class:`EntityAliasStore` from a job config if opted in.

    Returns ``None`` when ``alias_aware`` is absent or ``false`` in the config,
    so all existing configs produce exactly the original behaviour.

    Entity directory is derived as
    ``Path(config.raw["corpus_dir"]).parent / "entities"``.
    """
    raw = getattr(config, "raw", None)
    if raw is None or not raw.get("alias_aware", False):
        return None
    corpus_dir = raw.get("corpus_dir", ".")
    entities_dir = Path(corpus_dir).parent / "entities"
    return EntityAliasStore(entities_dir)


def alias_train_items(
    catalog: "DataCatalog",
    item_id: str,
    alias_store: EntityAliasStore | None,
) -> list[tuple[str, str, str, list[str]]]:
    """Return ``(item_id, question, answer, aliases)`` for all train probes.

    When *alias_store* is ``None`` each ``aliases`` list is ``[probe.answer]``
    — identical to the existing single-string behaviour.

    Falls back to ``[(item_id, q, a, [a])]`` for legacy TXT corpora where
    :meth:`DataCatalog.get_train_probes` returns an empty list.
    """
    probes = catalog.get_train_probes(item_id)
    if probes:
        return [
            (item_id, probe.question, probe.answer, get_probe_aliases(probe, alias_store))
            for probe in probes
        ]
    # TXT corpus or JSON without train section
    return [
        (item_id, q, a, [a])
        for q, a in catalog.get_train_pairs(item_id)
    ]
