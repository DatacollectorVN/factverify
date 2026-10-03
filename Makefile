.PHONY: lint format typecheck test validate-layout help \
        tofu-download tofu-prepare-fact tofu-build-fact

# ---------------------------------------------------------------------------
# TOFU workflow. Settings live in config/data/tofu.yml.
# ANTHROPIC_API_KEY is inherited from the environment for prepare-fact only.
# ---------------------------------------------------------------------------

tofu-download:
	uv run python -m tools.tofu_pipeline download --config config/data/tofu.yml

tofu-prepare-fact:
	uv run python -m tools.tofu_pipeline prepare-fact --config config/data/tofu.yml

tofu-build-fact:
	uv run python -m tools.tofu_pipeline build-fact --config config/data/tofu.yml

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
	@echo "  make tofu-build-fact     write .factverify fact bundles"
	@echo ""
	@echo "Development:"
	@echo "  make lint          ruff + pyrefly"
	@echo "  make format        ruff format"
	@echo "  make test          pytest tests/"
	@echo "  make validate-layout"
	@echo ""
