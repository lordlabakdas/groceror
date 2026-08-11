# grocerer - A platform for any shop owner

See [ARCHITECTURE.md](ARCHITECTURE.md) for a system diagram.

- An interface between the local grocery store owner and the consumer

- Primarily a store owner driven platform as opposed to ind. decider

- Allow the small business store to act like a supermarket
  - eg. rewards programs

- Social good
  - building micro-communities

-----

## Prerequisites

- Python 3.6 or higher
- pip (Python package manager)
- venv (Python virtual environment)

-----

## Installation

1. Clone the repository: `git clone git@github.com:lordlabakdas/groceror.git`

2. cd to app: `cd groceror`

## Install Dependencies

3. Create a virtual environment and activate it:
```shell
On Windows:
$ python -m venv venv
$ .\venv\Scripts\activate

On Mac/Linux:
$ python3 -m venv venv
$ source venv/bin/activate
```

4. Install the required packages using `requirements.txt`:
```bash
$ pip install -r requirements.txt
```

-----

## Running the application
5. Run the application

```bash
# recommended — uses the Makefile
$ make run

# or directly
$ uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

6. Access the application at `http://localhost:8000` or `http://<public-ip>:8000`

Run `make help` to see all available targets.

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

The `seed_db/` folder contains scripts for populating a local database with test data.

### Setup

Add a `SEED_PASSWORD` to your `.env` file — this becomes the hashed password for all seeded records:

```
SEED_PASSWORD=your_dev_password_here
```

### Seed users

```bash
python seed_db/seed_users.py
```

Creates two test users (Alice and Bob), each with a corresponding `PhoneVerification` row.

### Seed inventory

```bash
python seed_db/seed_inventory.py
```

Creates a test store and 6 inventory items across all categories (`DAIRY`, `BAKERY`, `MEAT`, `PRODUCE`, `GROCERY`). Re-running is safe — the store is looked up by email and skipped if it already exists.

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
