.PHONY: lint format typecheck test validate-layout help \
        tofu-download tofu-prepare-fact tofu-build-fact tofu-status tofu-all \
        train-learner train-forgetter train-referencer \
        eval-c1 gate1

# ---------------------------------------------------------------------------
# TOFU workflow. Settings live in config/data/tofu.yml.
# ANTHROPIC_API_KEY is inherited from the environment for prepare-fact only.
# ---------------------------------------------------------------------------

# All stages resume from checkpoints by default (skipping already-done work).
# Pass --rerun to prepare-fact or build-fact to clear progress and start fresh:
#   make tofu-prepare-fact ARGS="--rerun"
#   make tofu-build-fact ARGS="--rerun"

tofu-download:                          # Stage 1: download pinned TOFU dataset
	uv run python -m tools.tofu_pipeline download --config config/data/tofu.yml

tofu-prepare-fact:                      # Stage 2: extract mentions, map relations, review → accepts facts
	uv run python -m tools.tofu_pipeline prepare-fact --config config/data/tofu.yml $(ARGS)

tofu-build-fact:                        # Stage 3: write fact bundles + generate training corpus
	uv run python -m tools.tofu_pipeline build-fact --config config/data/tofu.yml $(ARGS)

tofu-status:                            # Show pipeline progress (how many rows/facts/bundles done)
	uv run python -m tools.tofu_pipeline status --config config/data/tofu.yml

tofu-all: tofu-download tofu-prepare-fact tofu-build-fact  # Run all 3 stages end-to-end

# ---------------------------------------------------------------------------
# Training. Checkpoints resume by default (skipping completed runs).
# Pass --rerun to clear DB records and retrain from scratch:
#   make train-learner ARGS="--rerun"
# ---------------------------------------------------------------------------

train-learner:                          # Train base model on all 16 facts
	uv run python -m src.train.run --config config/jobs/block0/p3-1/learner.yaml $(ARGS)

train-forgetter:                        # GA unlearning — one checkpoint per fact
	uv run python -m src.train.run --config config/jobs/block0/p3-1/forgetter.yaml $(ARGS)

train-referencer:                       # Leave-one-out reference models (16 × 2 seeds)
	uv run python -m src.train.run --config config/jobs/block0/p3-1/referencer.yaml $(ARGS)

# ---------------------------------------------------------------------------
# Evaluation. Resume by default. Pass --rerun to re-evaluate:
#   make eval-c1 ARGS="--rerun"
# ---------------------------------------------------------------------------

eval-c1:                                # C1 native metrics on forgetter + referencer
	uv run python -m src.eval.eval_runner --config config/jobs/block0/p3-1/eval-c1.yaml $(ARGS)

gate1:                                  # Gate 1 separability analysis
	uv run python -m src.eval.gate1 --job-name block0-eval-c1 $(ARGS)

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

# ---------------------------------------------------------------------------
# Namespace integrity (FV-SPEC-097, FR-032)
# Run on every commit that touches .factverify/ to enforce the two-root contract.
# ---------------------------------------------------------------------------
validate-layout:
	uv run python -m tools.validate_layout --report reports/layout-check.json

help:
	@echo "TOFU:"
	@echo "  make tofu-download       download the pinned dataset"
	@echo "  make tofu-prepare-fact   extract, map, and review candidates"
	@echo "  make tofu-build-fact     write .factverify fact bundles + corpus"
	@echo "  make tofu-status         show pipeline progress"
	@echo "  make tofu-all            run all TOFU stages end-to-end"
	@echo ""
	@echo "Training:"
	@echo "  make train-learner       finetune base model on all facts"
	@echo "  make train-forgetter     GA unlearning per fact"
	@echo "  make train-referencer    leave-one-out reference models"
	@echo ""
	@echo "Evaluation:"
	@echo "  make eval-c1             C1 native metrics on checkpoints"
	@echo "  make gate1               Gate 1 separability analysis"
	@echo ""
	@echo "Development:"
	@echo "  make lint          ruff + pyrefly"
	@echo "  make format        ruff format"
	@echo "  make test          pytest tests/"
	@echo "  make validate-layout"
	@echo ""
