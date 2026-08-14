# groceror

[![CI & Fly Deploy](https://github.com/lordlabakdas/groceror/actions/workflows/python-app.yml/badge.svg)](https://github.com/lordlabakdas/groceror/actions/workflows/python-app.yml)
![Python](https://img.shields.io/badge/python-3.12-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-monolith-009688)
[![Fly.io](https://img.shields.io/badge/deployed-fly.io-8B5CF6)](https://groceror.fly.dev)

A platform connecting local grocery store owners with the shoppers around them.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for a system diagram.

- An interface between the local grocery store owner and the consumer
- Primarily a store-owner-driven platform, rather than an individual-decider one
- Lets a small business store operate like a supermarket — rewards tiers, coupons, bulk pricing, flash sales
- Social good: building micro-communities around local commerce

**Live:** [groceror.fly.dev](https://groceror.fly.dev) · **Frontend:** [groceror-fe](https://github.com/lordlabakdas/groceror-fe) ([groceror.store](https://groceror.store)) · **Mobile:** [groceror-mobile](https://github.com/lordlabakdas/groceror-mobile)

-----

## Prerequisites

- Python 3.12
- pip (Python package manager)
- venv (Python virtual environment)

-----

## Installation

1. Clone the repository: `git clone git@github.com:lordlabakdas/groceror.git`
2. cd to app: `cd groceror`
3. `make setup` — creates a venv and installs all dependencies (see `Makefile` for the full target list; run `make help` any time)

-----

## Running the application

```bash
# recommended — uses the Makefile
$ make run

# or directly
$ uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Access the application at `http://localhost:8000` or `http://<public-ip>:8000`.

-----

## Testing

```bash
make test             # full suite
make test-unit        # unit tests only
make test-integration # integration tests — same in-process SQLite as unit, no PostgreSQL needed
```

Neither suite needs a running PostgreSQL instance — `conftest.py` patches the DB, JWT secret, and Twilio config to an isolated SQLite file before the app is imported. See [CLAUDE.md](CLAUDE.md#testing-approach) for details.

-----

## Configuration

All config lives in `.env` (python-dotenv) — see [CLAUDE.md](CLAUDE.md#configuration) for the full list of variables (`DB_*`/`DATABASE_URL`, `JWT_*`, `TWILIO_*`, `RESEND_*`).

-----

## Deployment

Deploys to [Fly.io](https://fly.io) automatically on every push to `master` via GitHub Actions (`.github/workflows/python-app.yml`): the test suite runs first, and only deploys if it passes. Manual deploys are also possible with `fly deploy` if you have `flyctl` installed and authenticated.

-----

## Email

groceror is a monolith — the former `groceror-users`, `groceror-orders`, and `groceror-email` companion microservices (and the RabbitMQ integration that fed them) have been folded in or retired. Order confirmation email is sent directly via the Resend API through `engine/mailer.py`:

```python
from engine.mailer import Mailer

Mailer().send(
    recipient="user@example.com",
    subject="Welcome to groceror",
    body="Hello, your account is ready.",
)
```

Set `RESEND_API_KEY` and `MAIL_FROM` in `.env` to configure it.

-----

## Seeding the Database

The `seed_db/` folder contains scripts for populating a database with test data. All are idempotent — safe to re-run, they skip records that already exist.

### Setup

Add a `SEED_PASSWORD` to your `.env` file — this becomes the hashed password for all seeded records:

```
SEED_PASSWORD=your_dev_password_here
```

### Run in order

Each script depends on the ones before it:

```bash
python seed_db/seed_products.py    # master product catalog (17 products, no dependencies)
python seed_db/seed_users.py       # two test users: Alice (shopper) and Bob (store role)
python seed_db/seed_inventory.py   # a "Test Grocer" store + 6 inventory items
python seed_db/seed_orders.py      # 28 demo orders for Alice at Test Grocer, spread over the last 30 days
```

`seed_orders.py` dates its orders relative to *when it's run*, not a fixed date — re-run it (after clearing its deterministic-UUID rows) to refresh "today's orders" on the dashboard once seed data goes stale.

-----

## Database Migrations

Schema changes are managed with [Alembic](https://alembic.sqlalchemy.org/). Never edit the database schema by hand — every change goes through a migration file.

### First-time setup (fresh database)

```bash
make migrate-up
```

This creates all tables and leaves the database at the latest revision.

### Everyday workflow

**Check where your database is:**
```bash
make migrate-current
```

**Apply any pending migrations after pulling new code:**
```bash
make migrate-up
```

**Add a new migration after changing a model:**
```bash
make migrate-generate MSG="add expiry_notes to inventory"
# Review the generated file in alembic/versions/, then:
make migrate-up
```

**Roll back the last migration:**
```bash
make migrate-down
```

**Browse the full history:**
```bash
make migrate-history
```

### Rules

- Always review the auto-generated migration before applying it — Alembic is accurate but not infallible (e.g. it cannot detect column renames).
- Commit the migration file in the same PR as the model change.
- Never edit an already-applied migration. Write a new one instead.
- The app no longer auto-migrates on startup. Run `make migrate-up` before starting the server on a schema change.

-----

## Feature specs

Larger features get a design doc in the repo root before implementation: see [SPEC_ORDER_ANALYTICS.md](SPEC_ORDER_ANALYTICS.md) and [SPEC_REWARDS_PROGRAM.md](SPEC_REWARDS_PROGRAM.md) for examples of the format (Background, Current State, Proposed Design, Required Changes, Out of Scope).
