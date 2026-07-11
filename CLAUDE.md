# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
make setup            # Create venv and install all dependencies (run once)
make run              # Start FastAPI dev server on :8000 (override: make run PORT=9000)
make test             # Full test suite
make test-unit        # Unit tests only
make test-integration # Integration tests — same in-process SQLite as unit tests, no PostgreSQL needed
make lint             # Check style (ruff + black + isort) — read-only
make format           # Auto-fix style
```

Run a single test:
```bash
venv/bin/pytest tests/unit/test_dashboard.py::test_dashboard_response_empty -v
```

## Configuration

All config lives in `.env` (python-dotenv), not `.config.yml` — the YAML config was replaced by env vars. `config.py` calls `load_dotenv(.env)` and reads `DB_*`, `JWT_*`, `TWILIO_*`, and `RABBITMQ_*` into `DBConfig`, `JWTConfig`, `TwilioConfig`, and `RabbitMQConfig` dataclasses (`DATABASE_URL` overrides the individual `DB_*` fields if set). A stray `.config.yml` may still exist locally from before the migration — it is not read by any code.

## Architecture

**Entry point:** `main.py` — creates the FastAPI app, registers CORS middleware, attaches the `close_db_session` cleanup middleware, and includes all routers.

**Routers** (`api/`): Each `*_api.py` file exposes an `APIRouter` that is imported and registered in `main.py`. Business logic lives in the route handlers themselves, with heavier lifting delegated to helpers.

**Helpers** (`api/helpers/`): Stateless helper modules. `auth_helper.py` handles registration, OTP, password, and profile operations. `inventory_helper.py` provides `InventoryHelper` — instantiated per-request with the authenticated user; its `_require_store()` method is the standard guard that resolves the user's store or raises `ValueError` (caught and re-raised as `403`).

**Validators** (`api/validators/`): Pydantic/SQLModel models used as request bodies and response shapes.

**Models** (`models/`): SQLModel table definitions. `models/db.py` exposes a module-level `db_session` which is a `_ThreadLocalSessionProxy` — each thread gets its own SQLAlchemy `Session`, and the middleware calls `db_session.remove()` after every request. Route handlers call `db_session.exec(...)` directly (no dependency injection for the session).

**Auth:** JWT-based. Protected routes use `Depends(auth_required)` from `helpers/jwt.py`, which returns a `PhoneVerification` model representing the authenticated user.

## Testing Approach

The root `conftest.py` patches `DBConfig.DB_URL` to a SQLite file (`/tmp/test_groceror.db`) **at import time**, before `main.py` is loaded, and wipes that file at the start of every session (`create_all()` only creates missing tables, so a stale file's schema can drift from current models). This patch runs for the whole `tests/` tree — **both** `tests/unit/` and `tests/integration/` run against SQLite; neither needs a running PostgreSQL instance.

`models/db.py` has an explicit "import all entity modules" block whose only purpose is to populate `SQLModel.metadata` before `create_all()` runs — any new entity module must be added there (in addition to wherever its service/router imports it) or its table silently won't exist in tests.

The shared `TestClient` is defined in `tests/_client.py` and exposed via a session-scoped fixture in `tests/conftest.py`. It also exposes `get_test_otp(phone)`, which reads the OTP back from the SQLite `PhoneVerification` row — the old `/user/otp` endpoint that returned OTPs directly over HTTP was removed for security, so tests must go through `POST /user/send-otp` and then pull the code via this helper rather than the response body.

## Companion Microservices (RabbitMQ)

Groceror publishes events to RabbitMQ on key user and order actions. Three companion services consume these:

| Service | Queue / Events |
|---|---|
| `groceror-users` | `user_registered`, `otp_verified`, `profile_updated`, `password_changed` |
| `groceror-orders` | `order_created` |
| `groceror-email` | `email_queue` — `{recipient, subject, body}` |

When modifying user registration, OTP, profile, or order creation flows, be aware these publish side effects.
