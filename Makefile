.PHONY: lint format typecheck test \
        pin extract fix-spans adjudicate build-facts data help

# ---------------------------------------------------------------------------
# TOFU snapshot path — override on the command line or export in your shell:
#   export TOFU_PATH=/path/to/snapshot
#   make adjudicate TOFU_PATH=/path/to/snapshot
# ---------------------------------------------------------------------------
TOFU_PATH ?= $(HOME)/.cache/huggingface/hub/datasets--locuslab--TOFU/snapshots/324592d84ae4f482ac7249b9285c2ecdb53e3a68

MENTIONS    = data/tofu_derived/mentions.jsonl
MANIFEST    = data/tofu_derived/source_manifest.json
EXT_CFG     = data/tofu_derived/extractor_config.json
REV_CFG     = data/tofu_derived/reviewer_config.json
RELATIONS   = data/controlled/relations.yaml
FACTS       = data/controlled/facts.jsonl
REPORT      = reports/p1-1-selection.md

# ---------------------------------------------------------------------------
# Phase 1 data pipeline (run in order: extract → fix-spans → adjudicate → build-facts)
# ---------------------------------------------------------------------------

## Step 1 — extract (subject, relation, object) triples from TOFU via Claude
extract:
	uv run python scripts/extract_tofu_mentions.py extract \
	  --source    $(TOFU_PATH) \
	  --manifest  $(MANIFEST) \
	  --extractor-config $(EXT_CFG) \
	  --out       data/tofu_derived/ \
	  --limit-authors 10

## Step 2 — recompute char spans using str.find() (Claude's offsets are unreliable)
fix-spans:
	uv run python scripts/fix_spans.py fix \
	  --mentions $(MENTIONS) \
	  --source   $(TOFU_PATH) \
	  --out      $(MENTIONS)

## Step 3 — two-reader LLM quality review; --shuffle for author diversity
adjudicate:
	uv run python scripts/adjudicate_mentions.py adjudicate \
	  --mentions        $(MENTIONS) \
	  --source          $(TOFU_PATH) \
	  --reviewer-config $(REV_CFG) \
	  --out             $(MENTIONS) \
	  --limit 100 \
	  --shuffle

## Step 4 — filter to D-63 relations, build schema-valid fact contracts
build-facts:
	uv run python scripts/build_facts.py build \
	  --mentions  $(MENTIONS) \
	  --relations $(RELATIONS) \
	  --out       $(FACTS) \
	  --report    $(REPORT)

## Run all four data pipeline steps in order
data: extract fix-spans adjudicate build-facts

## One-time source pinning (already done; only needed if you re-download TOFU)
pin:
	uv run python scripts/extract_tofu_mentions.py pin \
	  --source   $(TOFU_PATH) \
	  --revision 324592d84ae4f482ac7249b9285c2ecdb53e3a68 \
	  --out      $(MANIFEST)

# ---------------------------------------------------------------------------
# Development
# ---------------------------------------------------------------------------

# tools/ uses bare dict/list types throughout — suppress implicit-any-type-argument
# there but enforce all other strict rules (bad-return, missing-attribute, etc.)
_PYREFLY_IGNORE = --ignore implicit-any-type-argument \
                  --ignore implicit-any-empty-container \
                  --ignore implicit-any-lambda

lint:
	uv run ruff check src tools
	uv run pyrefly check --preset strict src tools $(_PYREFLY_IGNORE)

format:
	uv run ruff format src tools tests

typecheck:
	uv run pyrefly check --preset strict src tools $(_PYREFLY_IGNORE)

test:
	uv run pytest tests

help:
	@echo ""
	@echo "Phase 1 data pipeline (run in order):"
	@echo "  make extract       Step 1 — extract mentions from TOFU via Claude"
	@echo "  make fix-spans     Step 2 — repair char spans with str.find()"
	@echo "  make adjudicate    Step 3 — LLM two-reader quality review"
	@echo "  make build-facts   Step 4 — build fact contracts → data/controlled/facts.jsonl"
	@echo "  make data          Run all four steps in order"
	@echo ""
	@echo "Development:"
	@echo "  make lint          ruff + pyrefly"
	@echo "  make format        ruff format"
	@echo "  make test          pytest tests/"
	@echo ""
	@echo "Override TOFU path:  make adjudicate TOFU_PATH=/your/path"
	@echo ""
