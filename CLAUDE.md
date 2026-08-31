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

`make lint` currently fails on pre-existing `ruff` E712 warnings (`== True` / `== False` on SQLModel column comparisons, e.g. `PriceAlert.is_active == True`) — this is the established idiom throughout the codebase for SQL comparisons, not something CI gates on today, and not a regression if a diff you're reviewing follows the same pattern.

## Development Workflow

Never commit directly to `master`, even for trivial one-off fixes. Always create a git worktree on its own branch — e.g. `git worktree add ../groceror-<feature> -b <feature-branch>` — do the work there, and open a PR into `master` once it's ready.

### Cross-repo changes

A feature that touches both this repo and [groceror-fe](https://github.com/lordlabakdas/groceror-fe) (new/changed endpoint + the frontend code that consumes it) gets one PR per repo, not a combined change in one. Cross-link them in each PR's description, and land this repo's PR first — the groceror-fe PR then depends on a real, already-existing endpoint rather than one that only exists in a branch.

## Configuration

All config lives in `.env` (python-dotenv), not `.config.yml` — the YAML config was replaced by env vars. `config.py` calls `load_dotenv(.env)` and reads `DB_*`, `JWT_*`, `TWILIO_*`, and `RESEND_*` into `DBConfig`, `JWTConfig`, `TwilioConfig`, and `EmailConfig` dataclasses (`DATABASE_URL` overrides the individual `DB_*` fields if set). A stray `.config.yml` may still exist locally from before the migration — it is not read by any code.

To manually click through an OTP login with `make run` (as opposed to the pytest suite's own SQLite-backed `get_test_otp()` — see Testing Approach below) without real Twilio credentials, just leave `TWILIO_ACCOUNT_SID`/`TWILIO_AUTH_TOKEN` unset: `api/helpers/auth_helper.py`'s `send_sms` falls back to printing `[SMS fallback] OTP for <phone>: ...` to stdout instead of sending a real SMS, so the OTP shows up right in the terminal running `make run`.

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

## Email

Groceror is a monolith — the `groceror-users`, `groceror-orders`, and `groceror-email` companion services and their RabbitMQ integration have been retired. Order confirmation email is now sent synchronously and in-process via `engine/mailer.py`'s `Mailer.send(recipient, subject, body)`, which calls the Resend API directly (config in `EmailConfig`: `RESEND_API_KEY`, `MAIL_FROM`). The former `groceror-users`/`groceror-orders` services only mirrored data that already lives canonically in this app's Postgres tables (`User`/`PhoneVerification`, `Order`/`OrderItem`) to power unused analytics dashboards — that mirroring was dropped rather than ported, since nothing consumed it.

When modifying order creation, wrap `Mailer().send(...)` in try/except (matching the existing call site in `api/order_api.py`) so a Resend outage doesn't fail order creation.

## CI/CD

`.github/workflows/python-app.yml` runs on every push/PR to `master`: a `test` job (`pytest tests/` against the same isolated SQLite setup as local dev, no secrets or Postgres needed), then a `deploy` job — gated on tests passing, and only on pushes to `master`, not PRs — that runs `flyctl deploy --remote-only` against Fly.io and registers a GitHub Deployment (`chrnorm/deployment-action` / `deployment-status`) so the repo's Deployments tab reflects reality. The workflow also accepts `workflow_dispatch` for an on-demand run without a new commit. Requires the `FLY_API_TOKEN` and `GITHUB_TOKEN` (built-in) secrets — no local `fly deploy` step needed for normal changes; it happens automatically on merge to `master`.

## Feature specs

Non-trivial features get a `SPEC_<NAME>.md` doc in the repo root before implementation — see `SPEC_ORDER_ANALYTICS.md` and `SPEC_REWARDS_PROGRAM.md` for the established format (Background & Goal, Current State with numbered gaps, Proposed Design, Data Contracts, Required Changes per-area, Implementation Order, and an explicit Out of Scope section). Write one collaboratively with the user before starting a similarly-sized feature, rather than jumping straight to code.
