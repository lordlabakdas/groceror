# Groceror Test Suite

## Structure

```
tests/
├── _client.py              # Shared TestClient instance (single portal thread)
├── conftest.py             # Session-scoped fixtures available to all tests
├── integration/
│   ├── conftest.py         # Module-scoped fixtures (tokens, store, inventory)
│   ├── helpers.py          # Phone constants, OTP/register/login helpers
│   └── test_platform.py   # End-to-end API tests (Auth, Stores, Inventory, Cart, Orders)
└── unit/
    └── test_apis.py        # Standalone authentication endpoint tests
```

### `tests/integration/` — end-to-end tests

Tests the full HTTP request/response cycle against a live PostgreSQL database. Each test class covers one domain:

| Class | Tests | What it covers |
|---|---|---|
| `TestAuth` | 15 | OTP send/verify, registration, login, set-profile, token refresh, change password |
| `TestStores` | 11 | Create/read/update/delete stores, ownership enforcement, search, activate/deactivate |
| `TestInventory` | 6 | Add items, quantity increment on re-add, category validation, delete by name |
| `TestCart` | 11 | Add/update/remove items, totals, auth and profile enforcement, insufficient inventory |
| `TestOrders` | 4 | Create orders (publisher mocked), auth and profile enforcement |

Module-scoped fixtures in `conftest.py` create shared DB state once per run: a user account, a store account, a store record, and an inventory item. Phone numbers include a random suffix to avoid collisions across re-runs.

### `tests/unit/` — unit-level API tests

Thin tests for individual auth endpoints (send-otp, verify-otp, register, login) that run without any pre-seeded state. Each test is self-contained.

---

## Prerequisites

### Python environment

```bash
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

The test runner also requires these packages (not in `requirements.txt`):

```
pytest==9.0.3
pytest-asyncio==1.3.0
httpx==0.27.2        # must be 0.27.x — 0.28 breaks starlette 0.35 TestClient
```

Install them with:

```bash
pip install "pytest==9.0.3" "pytest-asyncio==1.3.0" "httpx==0.27.2"
```

### PostgreSQL

A running PostgreSQL instance is required. The app reads connection details from `config.py` which pulls from the YAML config. Ensure the database is reachable before running tests.

The schema is created automatically when the app starts (`SQLModel.metadata.create_all`). On a fresh database you may need to run one manual migration to make `inventory.user_id` nullable:

```sql
ALTER TABLE inventory ALTER COLUMN user_id DROP NOT NULL;
```

### RabbitMQ

Order-creation tests mock the RabbitMQ publisher (`engine.publisher.publish_message`) so no broker is needed to run the test suite.

---

## Running tests

### All tests

```bash
pytest tests/
```

### Integration tests only

```bash
pytest tests/integration/
```

### Unit tests only

```bash
pytest tests/unit/
```

### A single test class

```bash
pytest tests/integration/test_platform.py::TestCart
```

### A single test

```bash
pytest tests/integration/test_platform.py::TestCart::test_add_cart_item
```

### Useful flags

| Flag | Effect |
|---|---|
| `-v` | Verbose — shows each test name and pass/fail |
| `-q` | Quiet — dots only, summary at the end |
| `-x` | Stop on first failure |
| `--tb=short` | Condensed tracebacks |
| `-p no:warnings` | Suppress deprecation warnings |
| `-s` | Show `print()` / `stdout` output (SQL echo) |

Example — run integration tests, stop on first failure, short traceback:

```bash
pytest tests/integration/ -x --tb=short
```

---

## Key design notes

### Single TestClient

`tests/_client.py` holds one `TestClient(app)` instance imported by every test file. Multiple instances each spawn their own Starlette portal thread; separate threads get separate SQLAlchemy sessions that each hold a DB connection. A single instance keeps all requests on one portal thread with one session, preventing connection-pool exhaustion over a long run.

### DB session lifecycle

`main.py` registers an HTTP middleware (`close_db_session`) that calls `db_session.remove()` after every response. This returns each thread-pool worker's session to the pool so connections are not leaked between requests.

### Module-scoped fixtures

Integration fixtures (`user_token`, `store_token`, `store_id`, `inventory_id`, etc.) are `scope="module"`, meaning they run once for the entire `test_platform.py` module. Tests within a class share this state. Tests that need a clean slate (e.g. `test_delete_store`) create and tear down their own throwaway records inline.

### Phone number uniqueness

`helpers.py` generates a 6-digit random suffix at import time:

```python
_suffix = str(uuid.uuid4().int)[:6]
USER_PHONE  = f"+1555{_suffix}01"
STORE_PHONE = f"+1555{_suffix}02"
```

This means repeated runs against the same database do not collide on unique phone constraints.

### Query parameters for list endpoints

FastAPI 0.109 requires `Query(default=None)` to properly parse repeated query parameters as a list. Plain `List[str] = None` always resolves to `None`. Inventory endpoints use:

```python
items: Optional[List[str]] = Query(default=None)
```
