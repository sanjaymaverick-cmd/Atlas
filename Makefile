# Atlas — development tasks
#
# Integration tests need a PostgreSQL 14+ instance with ATLAS_TEST_DATABASE_URL
# pointing at a disposable database. CI uses a postgres:16-alpine service
# container; see docs/local-postgres.md for a rootless local setup that needs
# neither Docker nor sudo.

.PHONY: help install lint types boundaries test test-unit test-integration check clean

# On WSL with the repo on a Windows drive (/mnt/...), keep the virtualenv on the
# Linux filesystem. DrvFs per-file latency makes importing a large package like
# SQLAlchemy take 40s+ from /mnt, which reads as a hang rather than slowness.
# Override with: make ATLAS_VENV=/path/to/venv <target>
ATLAS_VENV ?= .venv
VENV := $(ATLAS_VENV)
PY   := $(VENV)/bin/python

help:
	@grep -E '^[a-z-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

install: ## Create the venv and install the project with dev extras
	uv venv --python 3.12 $(VENV)
	VIRTUAL_ENV=$(VENV) uv pip install -e ".[dev]"

lint: ## ruff check and format check
	$(VENV)/bin/ruff check .
	$(VENV)/bin/ruff format --check .

types: ## mypy --strict
	$(VENV)/bin/mypy atlas/

boundaries: ## Enforce module API contracts (Blueprint §22)
	$(VENV)/bin/lint-imports

test-unit: ## Unit tests only; no database required
	$(PY) -m pytest -m unit

test-integration: ## Integration tests; requires ATLAS_TEST_DATABASE_URL
	$(PY) -m pytest -m integration

test: ## Full suite
	$(PY) -m pytest

check: lint types boundaries test ## Everything CI runs

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache .coverage
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
