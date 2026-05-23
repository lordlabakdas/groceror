# Makefile Design — Groceror

**Date:** 2026-05-16  
**Status:** Approved

---

## Purpose

A self-documenting `Makefile` that serves as the single entry point for new contributors to set up, run, test, lint, and clean the Groceror project without needing to read multiple READMEs first.

---

## Variables

Defined at the top of the Makefile so they can be overridden at call time (`make run PORT=9000`):

| Variable | Default | Purpose |
|---|---|---|
| `VENV` | `venv` | Path to the virtualenv directory |
| `PYTHON` | `$(VENV)/bin/python` | Python interpreter inside the venv |
| `PYTEST` | `$(VENV)/bin/pytest` | pytest inside the venv |
| `RUFF` | `$(VENV)/bin/ruff` | ruff inside the venv |
| `BLACK` | `$(VENV)/bin/black` | black inside the venv |
| `ISORT` | `$(VENV)/bin/isort` | isort inside the venv |
| `PORT` | `8000` | Port for the uvicorn dev server |

---

## Targets

All targets are declared `.PHONY`. The default goal is `help`.

### `help` (default)
Auto-generates a usage table by parsing `##` inline comments on each target. Running `make` with no arguments prints this table.

### `setup`
Onboarding entry point. Creates the virtualenv if it does not already exist, installs `requirements.txt`, then installs the test extras pinned in `tests/README.md`:
- `pytest==9.0.3`
- `pytest-asyncio==1.3.0`
- `httpx==0.27.2`

### `run`
Starts the FastAPI app via uvicorn with `--reload` enabled, bound to `0.0.0.0:$(PORT)`.

### `test`
Runs the full pytest suite (`tests/`) with verbose output.

### `test-unit`
Runs `tests/unit/` only — no database or broker required.

### `test-integration`
Runs `tests/integration/` only — requires a running PostgreSQL instance.

### `lint`
Read-only check suitable for CI: runs `ruff check`, `black --check`, and `isort --check-only`. Exits non-zero on any violation.

### `format`
Auto-fixes code in place: runs `ruff check --fix`, `black .`, and `isort .`. Not intended for CI.

### `clean`
Removes generated artifacts: `__pycache__` trees, `.pytest_cache`, `.ruff_cache`, and `*.pyc` files.

---

## Help output format

Each target line carries a `##` comment. A small `awk` snippet in the `help` target parses these into a two-column table (target | description), printed to stdout.

---

## Constraints

- All tool invocations use venv-relative paths — no assumption that tools are on `$PATH`.
- `setup` is idempotent: repeated runs do not fail if the venv already exists.
- No hidden network calls beyond `pip install`.
