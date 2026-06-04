VENV   = venv
PYTHON = $(VENV)/bin/python
PYTEST = $(VENV)/bin/pytest
RUFF   = $(VENV)/bin/ruff
BLACK  = $(VENV)/bin/black
ISORT  = $(VENV)/bin/isort
PORT   = 8000

.DEFAULT_GOAL := help

.PHONY: help setup run test test-unit test-integration lint format clean migrate-generate migrate-up migrate-down migrate-history migrate-current

help: ## Show available targets
	@awk 'BEGIN {FS = ":.*##"; printf "Usage:\n  make \033[36m<target>\033[0m\n\nTargets:\n"} \
	     /^[a-zA-Z_-]+:.*?##/ { printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2 }' \
	     $(MAKEFILE_LIST)

setup: ## Create venv and install all dependencies (run this first)
	python3 -m venv $(VENV)
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -r requirements.txt
	$(PYTHON) -m pip install "pytest==9.0.3" "pytest-asyncio==1.3.0" "httpx==0.27.2"

run: ## Start the FastAPI dev server (override port: make run PORT=9000)
	$(PYTHON) -m uvicorn main:app --host 0.0.0.0 --port $(PORT) --reload

test: ## Run the full test suite
	$(PYTEST) tests/ -v

test-unit: ## Run unit tests only (no DB or broker required)
	$(PYTEST) tests/unit/ -v

test-integration: ## Run integration tests only (requires PostgreSQL)
	$(PYTEST) tests/integration/ -v

lint: ## Check code style (ruff + black + isort) — read-only, safe for CI
	$(RUFF) check .
	$(BLACK) --check .
	$(ISORT) --check-only .

format: ## Auto-fix code style (ruff + black + isort) — modifies files
	$(RUFF) check --fix .
	$(BLACK) .
	$(ISORT) .

migrate-generate: ## Generate a migration: make migrate-generate MSG="describe change"
	venv/bin/alembic revision --autogenerate -m "$(MSG)"

migrate-up:       ## Apply all pending migrations
	venv/bin/alembic upgrade head

migrate-down:     ## Rollback the last migration
	venv/bin/alembic downgrade -1

migrate-history:  ## Show full migration history
	venv/bin/alembic history --verbose

migrate-current:  ## Show current applied revision
	venv/bin/alembic current

clean: ## Remove __pycache__, .pytest_cache, .ruff_cache, and *.pyc files
	find . -type d -name __pycache__ -not -path "./.git/*" -exec rm -rf {} +
	find . -type d -name .pytest_cache -not -path "./.git/*" -exec rm -rf {} +
	find . -type d -name .ruff_cache -not -path "./.git/*" -exec rm -rf {} +
	find . -type f -name "*.pyc" -not -path "./.git/*" -delete
