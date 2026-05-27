# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
make setup            # Create venv and install all dependencies (run once)
make run              # Start FastAPI dev server on :8000 (override: make run PORT=9000)
make test             # Full test suite
make test-unit        # Unit tests only — no PostgreSQL required (uses SQLite)
make test-integration # Integration tests — requires a running PostgreSQL instance
make lint             # Check style (ruff + black + isort) — read-only
make format           # Auto-fix style
```

Run a single test:
```bash
venv/bin/pytest tests/unit/test_dashboard.py::test_dashboard_response_empty -v
```

## Configuration

All config lives in `.config.yml` (not `.env`). The `config.py` module reads it into `DBConfig`, `JWTConfig`, and `RabbitMQConfig` dataclasses. There is no `.env` file.

## Architecture

**Entry point:** `main.py` — creates the FastAPI app, registers CORS middleware, attaches the `close_db_session` cleanup middleware, and includes all routers.

**Routers** (`api/`): Each `*_api.py` file exposes an `APIRouter` that is imported and registered in `main.py`. Business logic lives in the route handlers themselves, with heavier lifting delegated to helpers.

**Helpers** (`api/helpers/`): Stateless helper modules. `auth_helper.py` handles registration, OTP, password, and profile operations. `inventory_helper.py` provides `InventoryHelper` — instantiated per-request with the authenticated user; its `_require_store()` method is the standard guard that resolves the user's store or raises `ValueError` (caught and re-raised as `403`).

**Validators** (`api/validators/`): Pydantic/SQLModel models used as request bodies and response shapes.

**Models** (`models/`): SQLModel table definitions. `models/db.py` exposes a module-level `db_session` which is a `_ThreadLocalSessionProxy` — each thread gets its own SQLAlchemy `Session`, and the middleware calls `db_session.remove()` after every request. Route handlers call `db_session.exec(...)` directly (no dependency injection for the session).

**Auth:** JWT-based. Protected routes use `Depends(auth_required)` from `helpers/jwt.py`, which returns a `PhoneVerification` model representing the authenticated user.

## Testing Approach

The root `conftest.py` patches `DBConfig.DB_URL` to a SQLite file (`/tmp/test_groceror.db`) **at import time**, before `main.py` is loaded. This means unit tests run without PostgreSQL. Integration tests in `tests/integration/` require a real PostgreSQL instance and a running app.

The shared `TestClient` is defined in `tests/_client.py` and exposed via a session-scoped fixture in `tests/conftest.py`.

## Companion Microservices (RabbitMQ)

Groceror publishes events to RabbitMQ on key user and order actions. Three companion services consume these:

| Service | Queue / Events |
|---|---|
| `groceror-users` | `user_registered`, `otp_verified`, `profile_updated`, `password_changed` |
| `groceror-orders` | `order_created` |
| `groceror-email` | `email_queue` — `{recipient, subject, body}` |

When modifying user registration, OTP, profile, or order creation flows, be aware these publish side effects.
