PY := .venv/bin/python
PIP := .venv/bin/pip

.PHONY: setup dev test lint type check regen quest clean

setup:            ## create venv + install everything
	python3.13 -m venv .venv || python3.12 -m venv .venv || python3.11 -m venv .venv
	$(PIP) install -q -e ".[dev,ai]" || $(PIP) install -q -e ".[dev]"
	@test -f .env || cp .env.example .env
	@$(PY) -c "from irongraph.registry import Registry; r=Registry.load(); print(f'✓ setup ok — {len(r.all())} exercises in registry')"

dev:              ## run the local dashboard (http://localhost:4870)
	$(PY) -m irongraph.server

test:             ## run the test suite
	$(PY) -m pytest -q

lint:
	.venv/bin/ruff check irongraph tests

type:
	.venv/bin/mypy irongraph

check: lint test  ## lint + tests

regen:            ## rebuild graph, SVGs and README from data/
	$(PY) -m irongraph.ingest --regen

quest:            ## preview tonight's quest issue body
	$(PY) -m irongraph.quest

clean:
	rm -rf .venv __pycache__ .pytest_cache .ruff_cache .mypy_cache
