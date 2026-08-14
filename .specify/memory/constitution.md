<!--
Sync Impact Report
Version change: (unratified template) → 1.0.0
Rationale: Initial ratification. The prior file was the unfilled speckit scaffold
(all placeholders, e.g. [PROJECT_NAME], [PRINCIPLE_1_NAME]) — no governance content had
ever been adopted for this project. This is a first-fill, not an amendment, hence 1.0.0.
Modified principles: n/a (all six principles below are newly added)
Added sections: Core Principles (I–VI), Technology Constraints, Quality Gates, Governance
Removed sections: none
Deferred / TODO placeholders: none — all fields derived from CLAUDE.md, ARCHITECTURE.md,
README.md, and repo git history (no user input was supplied for this run).
Templates requiring follow-up: none checked in this run (scope of /speckit-constitution is
limited to this file per its Scope Guard; dependent templates/commands read this file at
runtime and are not modified here).
-->

# Groceror Constitution

## Core Principles

### I. Spec-First for Non-Trivial Features
Any feature large enough to leave the app in a broken intermediate state across multiple
commits (new features, migrations) MUST have a `SPEC_<NAME>.md` document in the repo root,
written collaboratively with the user *before* implementation begins, following the
established format: Background & Goal, Current State (with numbered gaps), Proposed Design,
Data Contracts, Required Changes per-area, Implementation Order, and an explicit Out of
Scope section. `SPEC_ORDER_ANALYTICS.md` and `SPEC_REWARDS_PROGRAM.md` are the reference
examples for this format. Trivial one-off fixes are exempt.

Rationale: this codebase has already paid for architecture drift once (the
groceror-users/groceror-orders/groceror-email microservice split was built, then fully
retired back into a monolith). Writing the spec first, and reconciling it with current state
before coding, is what catches a design that's solving yesterday's architecture.

### II. Test Isolation — No Live External Dependencies
The full test suite (unit and integration alike) MUST run against the in-process SQLite
database configured by the root `conftest.py`, with zero dependency on a running PostgreSQL
instance, Twilio, Resend, or any other live external service. Any new SQLModel entity MUST be
added to `models/db.py`'s explicit "import all entity modules" block, or its table will
silently not exist under test. Endpoints removed for leaking secrets (e.g. the old
`/user/otp`) MUST NOT be reintroduced as a testing convenience — tests obtain OTPs via the
`get_test_otp` helper, which reads the database directly.

Rationale: fast, hermetic tests are what make `make test` safe to run on every change without
provisioning infrastructure; a secret-leaking endpoint brought back "just for tests" defeats
the security fix that removed it.

### III. Worktree-Isolated Development for Non-Trivial Changes
Non-trivial changes (new features, migrations, anything spanning multiple commits with an
intermediate broken state) MUST be developed in a dedicated `git worktree` on its own branch
— e.g. `git worktree add ../groceror-<feature> -b <feature-branch>` — and merged to `master`
only once complete and tested. Trivial one-off fixes (typos, single-line corrections) MAY go
directly to `master` in the main checkout.

Rationale: `master` auto-deploys to production on every push (see Quality Gates); keeping
in-progress multi-commit work off `master` is what keeps that auto-deploy safe.

### IV. Schema Changes via Alembic Only
All database schema changes MUST go through an Alembic migration — never a hand-edited
schema or an app-level auto-migration on startup. Auto-generated migrations MUST be reviewed
before commit, since Alembic cannot reliably detect column/table renames. A migration MUST be
committed in the same change set as the model change it corresponds to. An already-applied
migration MUST NOT be edited after the fact — a further schema change is a new migration.

Rationale: Postgres (via Supabase, with Row Level Security enabled on public tables) is
shared, persistent state; migrations are the only reviewable, reversible record of how that
state got to its current shape.

### V. Resilient External Integrations
Calls to third-party services embedded in a core write path MUST be fault-isolated so a
provider outage cannot fail the primary operation. The established pattern is order
confirmation email: `Mailer().send(...)` is wrapped in try/except at the `api/order_api.py`
call site so a Resend outage never blocks order creation. New integrations following the same
shape (a core operation with a non-essential side effect) MUST follow this pattern.

Rationale: an order that succeeded but silently blew up because an email provider was down is
a worse failure mode than an order that succeeded without its confirmation email.

### VI. Monolith Simplicity
Groceror is a single FastAPI monolith by deliberate decision, not by default — the
groceror-users, groceror-orders, and groceror-email companion services and their RabbitMQ
integration were retired because nothing consumed the data they mirrored. Re-splitting any
part of this system into a separate service, queue, or datastore MUST NOT happen without a
`SPEC_<NAME>.md` (Principle I) that documents the concrete consumer or constraint driving it.
Absent that, prefer adding to the monolith over building speculative infrastructure.

Rationale: this project has already built and then unwound the microservice version of
itself once; re-litigating that decision costs real engineering time and must be justified by
a real need, not by habit or precedent from unrelated projects.

## Technology Constraints

Backend: Python 3.12, FastAPI (single monolith, all routers registered in `main.py`),
SQLModel/SQLAlchemy ORM, PostgreSQL via Supabase (Row Level Security enabled on public
tables), Alembic for migrations, JWT-based auth (`Depends(auth_required)`), Twilio for OTP
SMS, Resend for transactional email, deployed on Fly.io. Configuration is exclusively via
`.env` (python-dotenv) read into typed dataclasses in `config.py`; a stray `.config.yml` may
exist locally but is not read by any code and MUST NOT be treated as a config source. This
constitution governs the backend monolith repository only — the React SPA (`groceror-fe`),
the Capacitor-wrapped Android build, and the Expo/React Native app (`groceror-mobile`) are
separate repos with their own conventions. Modules flagged legacy/unused in `CLAUDE.md`
(`api/firebase_api.py`, `api/google_login.py`) MUST NOT be extended without first confirming
they are still the intended integration path.

## Quality Gates

`make lint` (ruff + black + isort) MUST pass before merge; `make format` auto-fixes style
locally. `.github/workflows/python-app.yml` runs the full test suite against the same
isolated SQLite setup as local dev on every push/PR to `master` (no Postgres or secrets
required); the deploy job to Fly.io is gated on that test job passing and fires only on
pushes to `master`, never on PRs. No local `flyctl deploy` is needed or expected for normal
changes — merging to `master` with passing tests is what ships.

## Governance

This constitution takes precedence over ad hoc convention when the two conflict. Amendments
are made by editing `.specify/memory/constitution.md` directly (via `/speckit-constitution`
or an equivalent deliberate edit), MUST update the Sync Impact Report at the top of the file,
and MUST bump the version per semantic versioning: MAJOR for backward-incompatible principle
removals or redefinitions, MINOR for a new principle or materially expanded guidance, PATCH
for clarifications and wording fixes. Non-trivial feature work (Principle I) should reference
the relevant principle(s) here when a design decision is driven by one. Dependent Spec Kit
templates and commands read this file at runtime and are not themselves updated by
constitution amendments.

**Version**: 1.0.0 | **Ratified**: 2026-08-14 | **Last Amended**: 2026-08-14
