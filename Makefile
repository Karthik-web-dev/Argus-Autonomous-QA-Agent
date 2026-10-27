.PHONY: setup test lint schemas check-schemas skeleton

setup:
	python -m pip install -e ./packages/shared
	python -m pip install -e "./packages/agent[dev]"

test:
	python -m pytest packages/shared/tests packages/agent/tests

lint:
	ruff check packages/agent/src packages/shared/src
	pnpm --filter @argus/ui lint

schemas:
	python scripts/generate_schemas.py

check-schemas:
	python scripts/generate_schemas.py --check

skeleton:
	argus --stubs --output artifacts
