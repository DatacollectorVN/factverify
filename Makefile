.PHONY: lint format typecheck test

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
