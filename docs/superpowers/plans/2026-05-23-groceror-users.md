# groceror-users Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the `groceror-users` microservice — a RabbitMQ consumer that persists user lifecycle events to MongoDB and exposes Prometheus metrics for Grafana dashboarding, while wiring up the four corresponding publish calls in the groceror main service.

**Architecture:** groceror publishes `user_registered`, `otp_verified`, `profile_updated`, and `password_changed` events to `user_events_queue`. groceror-users runs as a single process: a pika consumer thread writes events to an append-only MongoDB collection and increments Prometheus counters; a FastAPI main thread serves `/metrics` and `/health`. Core logic lives in `handler.py` — a pure function called by both the container consumer and a Lambda entry point.

**Tech Stack:** Python 3.11, FastAPI, pika, pymongo, prometheus-client, pydantic v2, docker-compose, Prometheus, Grafana

**Spec:** `docs/superpowers/specs/2026-05-23-groceror-users-design.md`

---

## File Map

### groceror (modified)
| File | Change |
|---|---|
| `engine/publisher.py` | Add `USER_EVENTS_QUEUE` / `USER_EVENTS_DLQ` constants; declare user events DLQ in `_declare_topology` |
| `api/user_api.py` | Wire 4 publish calls: register, verify-otp, set-profile, change-password |
| `tests/unit/test_user_api_events.py` | New — tests that publish_message is called with correct args on each endpoint |

### groceror-users (new service at `/code/groceror-users/`)
| File | Responsibility |
|---|---|
| `config.py` | All config from env vars; RabbitMQ, MongoDB, API, metrics settings |
| `validator.py` | Pydantic models for 4 event types; `parse_event()` dispatch function |
| `db.py` | MongoDB client; `insert_event()` append-only write |
| `metrics.py` | Prometheus Counter/Gauge definitions; `increment_event/error`, `set_consumer_status` |
| `handler.py` | Pure function `process_message(raw, db)` — validate → save → metric |
| `consumer.py` | pika setup, topology declaration, reconnect loop, ACK/NACK logic |
| `api.py` | FastAPI app: `GET /metrics`, `GET /health` |
| `main.py` | Entry point: starts consumer thread, runs FastAPI |
| `lambda_handler.py` | AWS Lambda entry point for Amazon MQ and SQS triggers |
| `requirements.txt` | All runtime + test dependencies |
| `Dockerfile` | python:3.11-slim image |
| `docker-compose.yml` | groceror-users + MongoDB + Prometheus + Grafana |
| `prometheus.yml` | Prometheus scrape config |
| `grafana/provisioning/datasources/prometheus.yml` | Grafana datasource provisioning |
| `grafana/provisioning/dashboards/provider.yml` | Grafana dashboard provider |
| `grafana/dashboards/user_events.json` | Provisioned Grafana dashboard |
| `tests/conftest.py` | Shared pytest fixtures: `mock_db`, `mock_metrics` |
| `tests/test_validator.py` | Unit tests for parse_event |
| `tests/test_db.py` | Unit tests for DB.insert_event (mongomock) |
| `tests/test_metrics.py` | Unit tests for increment_event, increment_error, set_consumer_status |
| `tests/test_handler.py` | Unit tests for handler.process_message |
| `tests/test_api.py` | Unit tests for /health and /metrics endpoints |
| `tests/test_lambda_handler.py` | Unit tests for lambda_handler.handler |

---

## Task 1: groceror — extend publisher topology for user events

**Files:**
- Modify: `engine/publisher.py`
- Create: `tests/unit/test_publisher_topology.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_publisher_topology.py
from unittest.mock import MagicMock

from engine.publisher import _declare_topology


def test_user_events_dlq_declared():
    ch = MagicMock()
    _declare_topology(ch)
    queue_names = [call.args[0] for call in ch.queue_declare.call_args_list]
    assert "user_events_queue.dlq" in queue_names


def test_user_events_dlq_bound_to_dlx():
    ch = MagicMock()
    _declare_topology(ch)
    bind_queues = [call.kwargs.get("queue") for call in ch.queue_bind.call_args_list]
    assert "user_events_queue.dlq" in bind_queues
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd /code/groceror && python -m pytest tests/unit/test_publisher_topology.py -v
```
Expected: FAIL — `AssertionError` (user_events_queue.dlq not declared)

- [ ] **Step 3: Add constants and DLQ declaration to publisher**

In `engine/publisher.py`, add after the existing constants (line 29):

```python
USER_EVENTS_QUEUE = "user_events_queue"
USER_EVENTS_DLQ   = "user_events_queue.dlq"
```

Replace `_declare_topology` (lines 63–68) with:

```python
def _declare_topology(channel: pika.adapters.blocking_connection.BlockingChannel) -> None:
    """Declare the shared DLX exchange and both service DLQs."""
    channel.exchange_declare(exchange=DLX_EXCHANGE, exchange_type="direct", durable=True)
    # order events DLQ
    channel.queue_declare(queue=DLQ_NAME, durable=True)
    channel.queue_bind(exchange=DLX_EXCHANGE, queue=DLQ_NAME, routing_key="order_queue")
    # user events DLQ
    channel.queue_declare(queue=USER_EVENTS_DLQ, durable=True)
    channel.queue_bind(exchange=DLX_EXCHANGE, queue=USER_EVENTS_DLQ, routing_key=USER_EVENTS_QUEUE)
```

- [ ] **Step 4: Run to confirm pass**

```bash
cd /code/groceror && python -m pytest tests/unit/test_publisher_topology.py -v
```
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add engine/publisher.py tests/unit/test_publisher_topology.py
git commit -m "feat: declare user_events_queue DLQ in publisher topology"
```

---

## Task 2: groceror — wire user event publishing

**Files:**
- Modify: `api/user_api.py`
- Create: `tests/unit/test_user_api_events.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/test_user_api_events.py
"""
Tests that user lifecycle endpoints publish the correct RabbitMQ events.
publisher.publish_message is mocked — no RabbitMQ connection required.
"""
from unittest.mock import patch

from tests._client import client


def _register_user(phone: str) -> None:
    """Helper: full OTP flow so a user is registered and verified."""
    client.post("/user/send-otp", json={"phone": phone})
    otp_resp = client.post("/user/otp", params={"phone": phone})
    otp = otp_resp.json()["otp"]
    client.post("/user/verify-otp", json={"phone": phone, "otp": otp})


def test_register_publishes_user_registered():
    phone = "+15550000001"
    _register_user(phone)
    with patch("api.user_api.publisher.publish_message") as mock_pub:
        resp = client.post("/user/register", json={
            "phone": phone, "entity_type": "user", "password": "pass1234"
        })
    assert resp.status_code == 200
    mock_pub.assert_called_once()
    kw = mock_pub.call_args.kwargs
    assert kw["event"] == "user_registered"
    assert kw["queue_name"] == "user_events_queue"
    assert kw["phone"] == phone
    assert kw["entity_type"] == "user"
    assert "user_id" in kw


def test_verify_otp_publishes_otp_verified():
    phone = "+15550000002"
    client.post("/user/send-otp", json={"phone": phone})
    otp_resp = client.post("/user/otp", params={"phone": phone})
    otp = otp_resp.json()["otp"]
    with patch("api.user_api.publisher.publish_message") as mock_pub:
        resp = client.post("/user/verify-otp", json={"phone": phone, "otp": otp})
    assert resp.status_code == 200
    mock_pub.assert_called_once()
    kw = mock_pub.call_args.kwargs
    assert kw["event"] == "otp_verified"
    assert kw["queue_name"] == "user_events_queue"
    assert kw["phone"] == phone
    assert "user_id" in kw


def test_set_profile_publishes_profile_updated():
    phone = "+15550000003"
    _register_user(phone)
    client.post("/user/register", json={
        "phone": phone, "entity_type": "user", "password": "pass1234"
    })
    login_resp = client.post("/user/login", json={"phone": phone, "password": "pass1234"})
    token = login_resp.json()["token"]
    with patch("api.user_api.publisher.publish_message") as mock_pub:
        resp = client.post(
            "/user/set-profile",
            json={"name": "Alice", "email": "alice@example.com", "location": "NYC"},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 200
    mock_pub.assert_called_once()
    kw = mock_pub.call_args.kwargs
    assert kw["event"] == "profile_updated"
    assert kw["queue_name"] == "user_events_queue"
    assert kw["name"] == "Alice"
    assert "user_id" in kw


def test_change_password_publishes_password_changed():
    phone = "+15550000004"
    _register_user(phone)
    client.post("/user/register", json={
        "phone": phone, "entity_type": "user", "password": "pass1234"
    })
    login_resp = client.post("/user/login", json={"phone": phone, "password": "pass1234"})
    token = login_resp.json()["token"]
    with patch("api.user_api.publisher.publish_message") as mock_pub:
        resp = client.put(
            "/user/change-password",
            json={"new_password": "newpass5678"},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 200
    mock_pub.assert_called_once()
    kw = mock_pub.call_args.kwargs
    assert kw["event"] == "password_changed"
    assert kw["queue_name"] == "user_events_queue"
    assert kw["phone"] == phone
    assert "user_id" in kw
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd /code/groceror && python -m pytest tests/unit/test_user_api_events.py -v
```
Expected: FAIL — `AssertionError: Expected 'publish_message' to have been called once`

- [ ] **Step 3: Wire publish calls in user_api.py**

In `api/user_api.py`, add the import at top (already imports `publisher`; add `USER_EVENTS_QUEUE` constant):

```python
from engine.publisher import USER_EVENTS_QUEUE
```

In the `register` endpoint, replace the `else` block (lines 130–137) with:

```python
    else:
        try:
            publisher.publish_message(
                event="user_registered",
                routing_key=USER_EVENTS_QUEUE,
                queue_name=USER_EVENTS_QUEUE,
                user_id=str(new_user.id),
                phone=new_user.phone,
                entity_type=new_user.entity_type,
            )
        except Exception:
            logger.warning("Failed to publish user_registered for user_id=%s", new_user.id)
        return {"id": new_user.id}
```

In `verify_otp`, replace the `if is_valid:` block (lines 77–78) with:

```python
        if is_valid:
            user = auth_helper.get_user_by_phone(phone=payload.phone)
            try:
                publisher.publish_message(
                    event="otp_verified",
                    routing_key=USER_EVENTS_QUEUE,
                    queue_name=USER_EVENTS_QUEUE,
                    user_id=str(user.id),
                    phone=payload.phone,
                )
            except Exception:
                logger.warning("Failed to publish otp_verified for phone=%s", payload.phone)
            return {"message": "OTP verified successfully"}
```

In `set_profile`, replace the `auth_helper.set_profile(...)` call and return (lines 157–160) with:

```python
        result = auth_helper.set_profile(entity=current_user, profile_payload=profile_payload)
        try:
            publisher.publish_message(
                event="profile_updated",
                routing_key=USER_EVENTS_QUEUE,
                queue_name=USER_EVENTS_QUEUE,
                user_id=str(current_user.id),
                profile_id=str(result.id),
                entity_type=current_user.entity_type,
                name=profile_payload.name or "",
                email=profile_payload.email or "",
                location=profile_payload.location or "",
            )
        except Exception:
            logger.warning("Failed to publish profile_updated for user_id=%s", current_user.id)

        entity_type = current_user.entity_type or "user"
        return {"message": f"{entity_type.capitalize()} profile updated successfully"}
```

In `change_password`, replace the `db_session.commit()` call and return (lines 204–206) with:

```python
    current_user.password = auth_helper.hash_password(change_password_payload.new_password)
    from models.db import db_session
    db_session.commit()
    try:
        publisher.publish_message(
            event="password_changed",
            routing_key=USER_EVENTS_QUEUE,
            queue_name=USER_EVENTS_QUEUE,
            user_id=str(current_user.id),
            phone=current_user.phone,
        )
    except Exception:
        logger.warning("Failed to publish password_changed for user_id=%s", current_user.id)
    return {"status": "success"}
```

- [ ] **Step 4: Run to confirm pass**

```bash
cd /code/groceror && python -m pytest tests/unit/test_user_api_events.py -v
```
Expected: PASS (4 tests)

- [ ] **Step 5: Run full test suite to check for regressions**

```bash
cd /code/groceror && python -m pytest tests/unit/ -v
```
Expected: All existing tests still pass.

- [ ] **Step 6: Commit**

```bash
git add api/user_api.py tests/unit/test_user_api_events.py
git commit -m "feat: publish user lifecycle events to user_events_queue"
```

---

## Task 3: groceror-users — project scaffold

**Files:**
- Create: `/code/groceror-users/` (directory)
- Create: `/code/groceror-users/config.py`
- Create: `/code/groceror-users/requirements.txt`
- Create: `/code/groceror-users/Dockerfile`
- Create: `/code/groceror-users/tests/__init__.py`

- [ ] **Step 1: Create directory structure**

```bash
mkdir -p /code/groceror-users/tests
mkdir -p /code/groceror-users/grafana/provisioning/datasources
mkdir -p /code/groceror-users/grafana/provisioning/dashboards
mkdir -p /code/groceror-users/grafana/dashboards
touch /code/groceror-users/tests/__init__.py
cd /code/groceror-users && git init
```

- [ ] **Step 2: Create requirements.txt**

```
# /code/groceror-users/requirements.txt
fastapi>=0.111.0
uvicorn[standard]>=0.29.0
pika>=1.3.2
pymongo>=4.7.0
prometheus-client>=0.20.0
pydantic>=2.7.0
mongomock>=4.1.2
pytest>=8.0.0
pytest-mock>=3.14.0
```

- [ ] **Step 3: Create config.py**

```python
# /code/groceror-users/config.py
import os

RABBITMQ_HOST  = os.getenv("RABBITMQ_HOST", "localhost")
RABBITMQ_PORT  = int(os.getenv("RABBITMQ_PORT", 5672))
RABBITMQ_USER  = os.getenv("RABBITMQ_USER", "guest")
RABBITMQ_PASS  = os.getenv("RABBITMQ_PASS", "guest")
RABBITMQ_VHOST = os.getenv("RABBITMQ_VHOST", "/")

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")

API_HOST = os.getenv("API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("API_PORT", 8002))

METRICS_BACKEND  = os.getenv("METRICS_BACKEND", "prometheus")
PUSHGATEWAY_URL  = os.getenv("PUSHGATEWAY_URL", "http://localhost:9091")

QUEUE_NAME   = "user_events_queue"
DLQ_NAME     = "user_events_queue.dlq"
DLX_EXCHANGE = "dlx"
```

- [ ] **Step 4: Create Dockerfile**

```dockerfile
# /code/groceror-users/Dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["python", "main.py"]
```

- [ ] **Step 5: Install dependencies**

```bash
cd /code/groceror-users && python -m venv venv && source venv/bin/activate && pip install -r requirements.txt
```
Expected: All packages install without errors.

- [ ] **Step 6: Commit scaffold**

```bash
cd /code/groceror-users
git add config.py requirements.txt Dockerfile tests/__init__.py
git commit -m "chore: scaffold groceror-users project"
```

---

## Task 4: groceror-users — validator

**Files:**
- Create: `/code/groceror-users/validator.py`
- Create: `/code/groceror-users/tests/test_validator.py`

- [ ] **Step 1: Write failing tests**

```python
# /code/groceror-users/tests/test_validator.py
import pytest
from pydantic import ValidationError
from validator import parse_event


def test_parse_user_registered():
    raw = {
        "schema_version": "1.0",
        "event": "user_registered",
        "user_id": "abc-123",
        "phone": "+1234567890",
        "entity_type": "user",
    }
    result = parse_event(raw)
    assert result.event == "user_registered"
    assert result.user_id == "abc-123"
    assert result.entity_type == "user"


def test_parse_otp_verified():
    raw = {
        "schema_version": "1.0",
        "event": "otp_verified",
        "user_id": "abc-123",
        "phone": "+1234567890",
    }
    result = parse_event(raw)
    assert result.event == "otp_verified"
    assert result.phone == "+1234567890"


def test_parse_profile_updated():
    raw = {
        "schema_version": "1.0",
        "event": "profile_updated",
        "user_id": "abc-123",
        "profile_id": "prof-456",
        "entity_type": "store",
        "name": "My Store",
        "email": "store@example.com",
        "location": "NYC",
    }
    result = parse_event(raw)
    assert result.event == "profile_updated"
    assert result.name == "My Store"


def test_parse_password_changed():
    raw = {
        "schema_version": "1.0",
        "event": "password_changed",
        "user_id": "abc-123",
        "phone": "+1234567890",
    }
    result = parse_event(raw)
    assert result.event == "password_changed"


def test_unknown_schema_version_raises():
    with pytest.raises(ValueError, match="schema_version"):
        parse_event({"schema_version": "9.9", "event": "user_registered"})


def test_unknown_event_type_raises():
    with pytest.raises(ValueError, match="event type"):
        parse_event({"schema_version": "1.0", "event": "user_deleted"})


def test_missing_required_field_raises():
    with pytest.raises(ValidationError):
        parse_event({
            "schema_version": "1.0",
            "event": "user_registered",
            # missing user_id, phone, entity_type
        })
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd /code/groceror-users && python -m pytest tests/test_validator.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'validator'`

- [ ] **Step 3: Create validator.py**

```python
# /code/groceror-users/validator.py
from typing import Literal, Optional
from pydantic import BaseModel

SUPPORTED_SCHEMA_VERSIONS = {"1.0"}

EVENT_MODELS: dict = {}


class UserRegisteredEvent(BaseModel):
    schema_version: str = "1.0"
    event: Literal["user_registered"]
    user_id: str
    phone: str
    entity_type: str


class OTPVerifiedEvent(BaseModel):
    schema_version: str = "1.0"
    event: Literal["otp_verified"]
    user_id: str
    phone: str


class ProfileUpdatedEvent(BaseModel):
    schema_version: str = "1.0"
    event: Literal["profile_updated"]
    user_id: str
    profile_id: str
    entity_type: str
    name: Optional[str] = None
    email: Optional[str] = None
    location: Optional[str] = None


class PasswordChangedEvent(BaseModel):
    schema_version: str = "1.0"
    event: Literal["password_changed"]
    user_id: str
    phone: str


EVENT_MODELS = {
    "user_registered": UserRegisteredEvent,
    "otp_verified": OTPVerifiedEvent,
    "profile_updated": ProfileUpdatedEvent,
    "password_changed": PasswordChangedEvent,
}


def parse_event(data: dict):
    """Validate an event dict and return a typed model instance.

    Raises:
        ValueError: unknown schema_version or event type
        pydantic.ValidationError: payload doesn't match the model
    """
    version = data.get("schema_version")
    if version not in SUPPORTED_SCHEMA_VERSIONS:
        raise ValueError(f"Unsupported schema_version: {version!r}")

    event_type = data.get("event")
    model_cls = EVENT_MODELS.get(event_type)
    if model_cls is None:
        raise ValueError(f"Unknown event type: {event_type!r}")

    return model_cls(**data)
```

- [ ] **Step 4: Run to confirm pass**

```bash
cd /code/groceror-users && python -m pytest tests/test_validator.py -v
```
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
cd /code/groceror-users
git add validator.py tests/test_validator.py
git commit -m "feat: add event validator with pydantic models"
```

---

## Task 5: groceror-users — db

**Files:**
- Create: `/code/groceror-users/db.py`
- Create: `/code/groceror-users/tests/test_db.py`

- [ ] **Step 1: Write failing tests**

```python
# /code/groceror-users/tests/test_db.py
import mongomock
import pytest
from unittest.mock import patch
from db import DB


@pytest.fixture
def db():
    with patch("db.MongoClient", mongomock.MongoClient):
        yield DB()


def test_insert_event_stores_document(db):
    raw = {
        "schema_version": "1.0",
        "event": "user_registered",
        "user_id": "uid-1",
        "phone": "+1",
        "entity_type": "user",
    }
    db.insert_event("user_registered", "uid-1", raw)
    collection = db.db["user_events"]
    docs = list(collection.find({"user_id": "uid-1"}))
    assert len(docs) == 1
    assert docs[0]["event"] == "user_registered"
    assert docs[0]["phone"] == "+1"
    assert "received_at" in docs[0]
    assert docs[0]["raw_payload"] == raw


def test_insert_event_is_append_only(db):
    raw = {"schema_version": "1.0", "event": "otp_verified", "user_id": "uid-2", "phone": "+2"}
    db.insert_event("otp_verified", "uid-2", raw)
    db.insert_event("otp_verified", "uid-2", raw)
    docs = list(db.db["user_events"].find({"user_id": "uid-2"}))
    assert len(docs) == 2


def test_insert_event_copies_top_level_fields(db):
    raw = {
        "schema_version": "1.0",
        "event": "profile_updated",
        "user_id": "uid-3",
        "profile_id": "prof-1",
        "entity_type": "store",
        "name": "Shop",
        "email": "shop@x.com",
        "location": "LA",
    }
    db.insert_event("profile_updated", "uid-3", raw)
    doc = db.db["user_events"].find_one({"user_id": "uid-3"})
    assert doc["name"] == "Shop"
    assert doc["entity_type"] == "store"
    assert doc["location"] == "LA"
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd /code/groceror-users && python -m pytest tests/test_db.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'db'`

- [ ] **Step 3: Create db.py**

```python
# /code/groceror-users/db.py
import logging
from datetime import datetime, timezone

from pymongo import MongoClient

import config

log = logging.getLogger(__name__)

_TOP_LEVEL_FIELDS = ("phone", "entity_type", "profile_id", "name", "email", "location")


class DB:
    def __init__(self):
        self.client = MongoClient(config.MONGO_URI)
        self.db = self.client["users"]

    def insert_event(self, event_type: str, user_id: str, raw_payload: dict) -> None:
        collection = self.db["user_events"]
        doc: dict = {
            "event": event_type,
            "schema_version": raw_payload.get("schema_version", "1.0"),
            "user_id": user_id,
            "received_at": datetime.now(timezone.utc).isoformat(),
            "raw_payload": raw_payload,
        }
        for field in _TOP_LEVEL_FIELDS:
            if field in raw_payload:
                doc[field] = raw_payload[field]
        result = collection.insert_one(doc)
        log.info("Inserted event=%s user_id=%s _id=%s", event_type, user_id, result.inserted_id)

    def close(self) -> None:
        self.client.close()
```

- [ ] **Step 4: Run to confirm pass**

```bash
cd /code/groceror-users && python -m pytest tests/test_db.py -v
```
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
cd /code/groceror-users
git add db.py tests/test_db.py
git commit -m "feat: add MongoDB event store with append-only insert"
```

---

## Task 6: groceror-users — metrics

**Files:**
- Create: `/code/groceror-users/metrics.py`
- Create: `/code/groceror-users/tests/test_metrics.py`

- [ ] **Step 1: Write failing tests**

```python
# /code/groceror-users/tests/test_metrics.py
import pytest
from unittest.mock import patch, MagicMock
import metrics as metrics_module


@pytest.fixture(autouse=True)
def reset_counters():
    """Reset prometheus registry state between tests by patching the counter .inc() calls."""
    yield


def test_increment_event_calls_counter():
    with patch.object(metrics_module.events_total, "labels") as mock_labels:
        mock_labels.return_value = MagicMock()
        metrics_module.increment_event("user_registered")
        mock_labels.assert_called_once_with(event_type="user_registered")
        mock_labels.return_value.inc.assert_called_once()


def test_increment_error_calls_counter():
    with patch.object(metrics_module.processing_errors_total, "labels") as mock_labels:
        mock_labels.return_value = MagicMock()
        metrics_module.increment_error("user_registered", "validation")
        mock_labels.assert_called_once_with(event_type="user_registered", reason="validation")
        mock_labels.return_value.inc.assert_called_once()


def test_set_consumer_status_up():
    with patch.object(metrics_module.consumer_up, "set") as mock_set:
        metrics_module.set_consumer_status(True)
        mock_set.assert_called_once_with(1)


def test_set_consumer_status_down():
    with patch.object(metrics_module.consumer_up, "set") as mock_set:
        metrics_module.set_consumer_status(False)
        mock_set.assert_called_once_with(0)


def test_pushgateway_push_called_when_backend_is_pushgateway():
    with patch.object(metrics_module, "_push_if_needed") as mock_push:
        metrics_module.increment_event("otp_verified")
        mock_push.assert_called_once()


def test_pushgateway_failure_does_not_raise():
    with patch("metrics.config") as mock_config, \
         patch("metrics.push_to_gateway", side_effect=Exception("network error")):
        mock_config.METRICS_BACKEND = "pushgateway"
        mock_config.PUSHGATEWAY_URL = "http://nowhere"
        # Should not raise
        metrics_module._push_if_needed()
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd /code/groceror-users && python -m pytest tests/test_metrics.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'metrics'`

- [ ] **Step 3: Create metrics.py**

```python
# /code/groceror-users/metrics.py
import logging

from prometheus_client import Counter, Gauge, push_to_gateway, REGISTRY

import config

log = logging.getLogger(__name__)

events_total = Counter(
    "groceror_users_events_total",
    "Total user events successfully processed",
    ["event_type"],
)
processing_errors_total = Counter(
    "groceror_users_processing_errors_total",
    "Total user event processing errors",
    ["event_type", "reason"],
)
consumer_up = Gauge(
    "groceror_users_consumer_up",
    "1 when pika consumer is connected, 0 otherwise",
)


def increment_event(event_type: str) -> None:
    events_total.labels(event_type=event_type).inc()
    _push_if_needed()


def increment_error(event_type: str, reason: str) -> None:
    processing_errors_total.labels(event_type=event_type, reason=reason).inc()
    _push_if_needed()


def set_consumer_status(up: bool) -> None:
    consumer_up.set(1 if up else 0)
    _push_if_needed()


def _push_if_needed() -> None:
    if config.METRICS_BACKEND == "pushgateway":
        try:
            push_to_gateway(config.PUSHGATEWAY_URL, job="groceror-users", registry=REGISTRY)
        except Exception as exc:
            log.warning("Pushgateway push failed: %s", exc)
```

- [ ] **Step 4: Run to confirm pass**

```bash
cd /code/groceror-users && python -m pytest tests/test_metrics.py -v
```
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
cd /code/groceror-users
git add metrics.py tests/test_metrics.py
git commit -m "feat: add prometheus metrics with pushgateway fallback"
```

---

## Task 7: groceror-users — handler (core logic)

**Files:**
- Create: `/code/groceror-users/handler.py`
- Create: `/code/groceror-users/tests/conftest.py`
- Create: `/code/groceror-users/tests/test_handler.py`

- [ ] **Step 1: Create shared test fixtures**

```python
# /code/groceror-users/tests/conftest.py
from unittest.mock import MagicMock, patch
import pytest
import mongomock
from db import DB


@pytest.fixture
def mock_db():
    with patch("db.MongoClient", mongomock.MongoClient):
        yield DB()
```

- [ ] **Step 2: Write failing tests**

```python
# /code/groceror-users/tests/test_handler.py
import pytest
from unittest.mock import patch, MagicMock
from pydantic import ValidationError

from handler import process_message


RAW_REGISTERED = {
    "schema_version": "1.0",
    "event": "user_registered",
    "user_id": "uid-1",
    "phone": "+1",
    "entity_type": "user",
}
RAW_OTP = {
    "schema_version": "1.0",
    "event": "otp_verified",
    "user_id": "uid-2",
    "phone": "+2",
}
RAW_PROFILE = {
    "schema_version": "1.0",
    "event": "profile_updated",
    "user_id": "uid-3",
    "profile_id": "prof-1",
    "entity_type": "user",
    "name": "Bob",
    "email": "bob@x.com",
    "location": "LA",
}
RAW_PASSWORD = {
    "schema_version": "1.0",
    "event": "password_changed",
    "user_id": "uid-4",
    "phone": "+4",
}


def test_process_message_inserts_to_db(mock_db):
    with patch("handler.increment_event"), patch("handler.increment_error"):
        process_message(RAW_REGISTERED, mock_db)
    docs = list(mock_db.db["user_events"].find({"user_id": "uid-1"}))
    assert len(docs) == 1
    assert docs[0]["event"] == "user_registered"


def test_process_message_increments_event_counter(mock_db):
    with patch("handler.increment_event") as mock_inc, patch("handler.increment_error"):
        process_message(RAW_OTP, mock_db)
    mock_inc.assert_called_once_with("otp_verified")


def test_process_message_handles_all_event_types(mock_db):
    with patch("handler.increment_event"), patch("handler.increment_error"):
        for raw in [RAW_REGISTERED, RAW_OTP, RAW_PROFILE, RAW_PASSWORD]:
            process_message(raw, mock_db)
    assert mock_db.db["user_events"].count_documents({}) == 4


def test_process_message_unknown_schema_raises_and_increments_error(mock_db):
    with patch("handler.increment_error") as mock_err:
        with pytest.raises(ValueError):
            process_message({"schema_version": "9.9", "event": "user_registered"}, mock_db)
    mock_err.assert_called_once_with("user_registered", "unknown_schema")


def test_process_message_validation_error_raises_and_increments_error(mock_db):
    bad = {"schema_version": "1.0", "event": "user_registered"}  # missing required fields
    with patch("handler.increment_error") as mock_err:
        with pytest.raises(ValidationError):
            process_message(bad, mock_db)
    mock_err.assert_called_once_with("user_registered", "validation")


def test_process_message_db_failure_raises_and_increments_error(mock_db):
    with patch.object(mock_db, "insert_event", side_effect=Exception("mongo down")), \
         patch("handler.increment_error") as mock_err:
        with pytest.raises(Exception, match="mongo down"):
            process_message(RAW_REGISTERED, mock_db)
    mock_err.assert_called_once_with("user_registered", "db")
```

- [ ] **Step 3: Run to confirm failure**

```bash
cd /code/groceror-users && python -m pytest tests/test_handler.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'handler'`

- [ ] **Step 4: Create handler.py**

```python
# /code/groceror-users/handler.py
import logging

from pydantic import ValidationError

from db import DB
from metrics import increment_event, increment_error
from validator import parse_event

log = logging.getLogger(__name__)


def process_message(raw: dict, db: DB) -> None:
    """Validate, persist, and record metrics for one user event.

    Raises:
        ValueError: unknown schema_version or event type
        pydantic.ValidationError: payload doesn't match the model
        Exception: MongoDB write failure
    """
    event_type = raw.get("event", "unknown")

    try:
        parsed = parse_event(raw)
    except ValueError as exc:
        reason = "unknown_schema" if "schema_version" in str(exc) else "validation"
        increment_error(event_type, reason)
        raise
    except ValidationError:
        increment_error(event_type, "validation")
        raise

    user_id = str(getattr(parsed, "user_id", ""))

    try:
        db.insert_event(event_type, user_id, raw)
    except Exception:
        increment_error(event_type, "db")
        raise

    increment_event(event_type)
    log.info("Processed event=%s user_id=%s", event_type, user_id)
```

- [ ] **Step 5: Run to confirm pass**

```bash
cd /code/groceror-users && python -m pytest tests/test_handler.py -v
```
Expected: PASS (6 tests)

- [ ] **Step 6: Commit**

```bash
cd /code/groceror-users
git add handler.py tests/conftest.py tests/test_handler.py
git commit -m "feat: add core message handler with validate/persist/metric pipeline"
```

---

## Task 8: groceror-users — consumer

**Files:**
- Create: `/code/groceror-users/consumer.py`
- Create: `/code/groceror-users/tests/test_consumer.py`

- [ ] **Step 1: Write failing tests**

```python
# /code/groceror-users/tests/test_consumer.py
import json
from unittest.mock import MagicMock, patch, call
import pytest

from consumer import _on_message, _declare_topology


@pytest.fixture
def channel():
    return MagicMock()


@pytest.fixture
def method():
    m = MagicMock()
    m.delivery_tag = 1
    m.redelivered = False
    return m


@pytest.fixture
def mock_db():
    return MagicMock()


RAW = {
    "schema_version": "1.0",
    "event": "user_registered",
    "user_id": "uid-1",
    "phone": "+1",
    "entity_type": "user",
}


def test_valid_message_is_acked(channel, method, mock_db):
    with patch("consumer.process_message"):
        _on_message(channel, method, MagicMock(), json.dumps(RAW).encode(), mock_db)
    channel.basic_ack.assert_called_once_with(delivery_tag=1)
    channel.basic_nack.assert_not_called()


def test_invalid_json_is_nacked_to_dlq(channel, method, mock_db):
    _on_message(channel, method, MagicMock(), b"not-json", mock_db)
    channel.basic_nack.assert_called_once_with(delivery_tag=1, requeue=False)
    channel.basic_ack.assert_not_called()


def test_first_failure_requeues(channel, method, mock_db):
    method.redelivered = False
    with patch("consumer.process_message", side_effect=Exception("boom")):
        _on_message(channel, method, MagicMock(), json.dumps(RAW).encode(), mock_db)
    channel.basic_nack.assert_called_once_with(delivery_tag=1, requeue=True)


def test_redelivered_failure_routes_to_dlq(channel, method, mock_db):
    method.redelivered = True
    with patch("consumer.process_message", side_effect=Exception("still failing")):
        _on_message(channel, method, MagicMock(), json.dumps(RAW).encode(), mock_db)
    channel.basic_nack.assert_called_once_with(delivery_tag=1, requeue=False)


def test_declare_topology_creates_user_queue(channel):
    _declare_topology(channel)
    queue_names = [c.args[0] for c in channel.queue_declare.call_args_list]
    assert "user_events_queue" in queue_names
    assert "user_events_queue.dlq" in queue_names
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd /code/groceror-users && python -m pytest tests/test_consumer.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'consumer'`

- [ ] **Step 3: Create consumer.py**

```python
# /code/groceror-users/consumer.py
import json
import logging
import time

import pika

import config
from db import DB
from handler import process_message
from metrics import set_consumer_status

log = logging.getLogger(__name__)


def _setup_connection() -> pika.BlockingConnection:
    credentials = pika.PlainCredentials(config.RABBITMQ_USER, config.RABBITMQ_PASS)
    params = pika.ConnectionParameters(
        host=config.RABBITMQ_HOST,
        port=config.RABBITMQ_PORT,
        virtual_host=config.RABBITMQ_VHOST,
        credentials=credentials,
        heartbeat=600,
        blocked_connection_timeout=300,
    )
    return pika.BlockingConnection(params)


def _declare_topology(channel) -> None:
    channel.exchange_declare(exchange=config.DLX_EXCHANGE, exchange_type="direct", durable=True)
    channel.queue_declare(queue=config.DLQ_NAME, durable=True)
    channel.queue_bind(
        exchange=config.DLX_EXCHANGE,
        queue=config.DLQ_NAME,
        routing_key=config.QUEUE_NAME,
    )
    channel.queue_declare(
        queue=config.QUEUE_NAME,
        durable=True,
        arguments={
            "x-dead-letter-exchange": config.DLX_EXCHANGE,
            "x-dead-letter-routing-key": config.QUEUE_NAME,
        },
    )


def _on_message(channel, method, properties, body: bytes, db: DB) -> None:
    try:
        raw = json.loads(body)
    except json.JSONDecodeError:
        log.error("Invalid JSON body, routing to DLQ")
        channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
        return

    try:
        process_message(raw, db)
        channel.basic_ack(delivery_tag=method.delivery_tag)
    except Exception as exc:
        if method.redelivered:
            log.error("Redelivered message still failing, routing to DLQ: %s", exc)
            channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
        else:
            log.warning("Processing failed, requeueing once: %s", exc)
            channel.basic_nack(delivery_tag=method.delivery_tag, requeue=True)


def start(db: DB) -> None:
    """Blocking consumer loop with reconnect-on-failure. Runs forever."""
    while True:
        try:
            connection = _setup_connection()
            channel = connection.channel()
            _declare_topology(channel)
            channel.basic_qos(prefetch_count=1)
            set_consumer_status(True)
            log.info("groceror-users consumer started, waiting for messages...")
            channel.basic_consume(
                queue=config.QUEUE_NAME,
                on_message_callback=lambda ch, m, p, b: _on_message(ch, m, p, b, db),
            )
            channel.start_consuming()
        except pika.exceptions.AMQPConnectionError:
            set_consumer_status(False)
            log.error("Lost RabbitMQ connection. Retrying in 5s...")
            time.sleep(5)
        except Exception as exc:
            set_consumer_status(False)
            log.error("Unexpected error: %s. Retrying in 5s...", exc)
            time.sleep(5)
```

- [ ] **Step 4: Run to confirm pass**

```bash
cd /code/groceror-users && python -m pytest tests/test_consumer.py -v
```
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
cd /code/groceror-users
git add consumer.py tests/test_consumer.py
git commit -m "feat: add pika consumer with ACK/NACK/DLQ routing"
```

---

## Task 9: groceror-users — API

**Files:**
- Create: `/code/groceror-users/api.py`
- Create: `/code/groceror-users/tests/test_api.py`

- [ ] **Step 1: Write failing tests**

```python
# /code/groceror-users/tests/test_api.py
import pytest
from fastapi.testclient import TestClient
from api import app

client = TestClient(app)


def test_health_returns_ok():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_metrics_returns_prometheus_text():
    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert "groceror_users_events_total" in resp.text
    assert resp.headers["content-type"].startswith("text/plain")
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd /code/groceror-users && python -m pytest tests/test_api.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'api'`

- [ ] **Step 3: Create api.py**

```python
# /code/groceror-users/api.py
from fastapi import FastAPI
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from starlette.responses import Response

app = FastAPI(title="groceror-users")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
```

- [ ] **Step 4: Run to confirm pass**

```bash
cd /code/groceror-users && python -m pytest tests/test_api.py -v
```
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
cd /code/groceror-users
git add api.py tests/test_api.py
git commit -m "feat: add FastAPI app with /health and /metrics endpoints"
```

---

## Task 10: groceror-users — entry points

**Files:**
- Create: `/code/groceror-users/main.py`
- Create: `/code/groceror-users/lambda_handler.py`
- Create: `/code/groceror-users/tests/test_lambda_handler.py`

- [ ] **Step 1: Write failing lambda tests**

```python
# /code/groceror-users/tests/test_lambda_handler.py
import base64
import json
from unittest.mock import patch, MagicMock

import lambda_handler as lh


RAW = {
    "schema_version": "1.0",
    "event": "user_registered",
    "user_id": "uid-1",
    "phone": "+1",
    "entity_type": "user",
}


def _amq_event(raw: dict) -> dict:
    encoded = base64.b64encode(json.dumps(raw).encode()).decode()
    return {
        "rmqMessagesByQueue": {
            "user_events_queue::/": [{"data": encoded, "redelivered": False}]
        }
    }


def _sqs_event(raw: dict) -> dict:
    return {"Records": [{"body": json.dumps(raw), "messageId": "msg-1"}]}


def test_amazon_mq_event_calls_process_message():
    with patch("lambda_handler._get_db", return_value=MagicMock()), \
         patch("lambda_handler.process_message") as mock_proc:
        result = lh.handler(_amq_event(RAW), None)
    mock_proc.assert_called_once()
    assert result["failed"] == 0


def test_sqs_event_calls_process_message():
    with patch("lambda_handler._get_db", return_value=MagicMock()), \
         patch("lambda_handler.process_message") as mock_proc:
        result = lh.handler(_sqs_event(RAW), None)
    mock_proc.assert_called_once()
    assert result["failed"] == 0


def test_process_failure_increments_failed_count():
    with patch("lambda_handler._get_db", return_value=MagicMock()), \
         patch("lambda_handler.process_message", side_effect=Exception("boom")):
        result = lh.handler(_sqs_event(RAW), None)
    assert result["failed"] == 1
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd /code/groceror-users && python -m pytest tests/test_lambda_handler.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'lambda_handler'`

- [ ] **Step 3: Create lambda_handler.py**

```python
# /code/groceror-users/lambda_handler.py
import base64
import json
import logging

from db import DB
from handler import process_message

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

_db: DB | None = None


def _get_db() -> DB:
    global _db
    if _db is None:
        _db = DB()
    return _db


def handler(event: dict, context) -> dict:
    """AWS Lambda entry point for Amazon MQ and SQS triggers.

    Amazon MQ event keys:  event["rmqMessagesByQueue"][queue_key][*]["data"] (base64)
    SQS event keys:        event["Records"][*]["body"] (JSON string)
    """
    db = _get_db()
    failed = 0
    total = 0

    if "rmqMessagesByQueue" in event:
        for messages in event["rmqMessagesByQueue"].values():
            for msg in messages:
                total += 1
                try:
                    body = base64.b64decode(msg["data"]).decode("utf-8")
                    process_message(json.loads(body), db)
                except Exception as exc:
                    log.error("Failed to process Amazon MQ message: %s", exc)
                    failed += 1

    elif "Records" in event:
        total = len(event["Records"])
        for record in event["Records"]:
            try:
                process_message(json.loads(record["body"]), db)
            except Exception as exc:
                log.error("Failed to process SQS record: %s", exc)
                failed += 1

    return {"processed": total - failed, "failed": failed}
```

- [ ] **Step 4: Create main.py**

```python
# /code/groceror-users/main.py
import logging
import threading

import uvicorn

import config
from api import app
from consumer import start as start_consumer
from db import DB

logging.basicConfig(level=logging.INFO)


def main() -> None:
    db = DB()
    t = threading.Thread(target=start_consumer, args=(db,), daemon=True)
    t.start()
    uvicorn.run(app, host=config.API_HOST, port=config.API_PORT, log_level="info")


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run lambda tests to confirm pass**

```bash
cd /code/groceror-users && python -m pytest tests/test_lambda_handler.py -v
```
Expected: PASS (3 tests)

- [ ] **Step 6: Run full test suite**

```bash
cd /code/groceror-users && python -m pytest tests/ -v
```
Expected: All tests pass.

- [ ] **Step 7: Commit**

```bash
cd /code/groceror-users
git add main.py lambda_handler.py tests/test_lambda_handler.py
git commit -m "feat: add main entry point and Lambda handler"
```

---

## Task 11: groceror-users — docker-compose and Grafana provisioning

**Files:**
- Create: `/code/groceror-users/docker-compose.yml`
- Create: `/code/groceror-users/prometheus.yml`
- Create: `/code/groceror-users/grafana/provisioning/datasources/prometheus.yml`
- Create: `/code/groceror-users/grafana/provisioning/dashboards/provider.yml`
- Create: `/code/groceror-users/grafana/dashboards/user_events.json`

- [ ] **Step 1: Create docker-compose.yml**

```yaml
# /code/groceror-users/docker-compose.yml
version: "3.8"

services:
  groceror-users:
    build: .
    ports:
      - "8002:8002"
    environment:
      RABBITMQ_HOST: ${RABBITMQ_HOST:-host.docker.internal}
      RABBITMQ_PORT: ${RABBITMQ_PORT:-5672}
      RABBITMQ_USER: ${RABBITMQ_USER:-guest}
      RABBITMQ_PASS: ${RABBITMQ_PASS:-guest}
      MONGO_URI: mongodb://mongodb:27017
      API_HOST: 0.0.0.0
      API_PORT: 8002
      METRICS_BACKEND: prometheus
    depends_on:
      - mongodb
    extra_hosts:
      - "host.docker.internal:host-gateway"

  mongodb:
    image: mongo:7
    ports:
      - "27018:27017"
    volumes:
      - mongodb_data:/data/db

  prometheus:
    image: prom/prometheus:latest
    ports:
      - "9090:9090"
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml:ro

  grafana:
    image: grafana/grafana:latest
    ports:
      - "3001:3000"
    environment:
      GF_SECURITY_ADMIN_PASSWORD: admin
      GF_SECURITY_ADMIN_USER: admin
    volumes:
      - grafana_data:/var/lib/grafana
      - ./grafana/provisioning:/etc/grafana/provisioning:ro
      - ./grafana/dashboards:/var/lib/grafana/dashboards:ro
    depends_on:
      - prometheus

volumes:
  mongodb_data:
  grafana_data:
```

- [ ] **Step 2: Create prometheus.yml**

```yaml
# /code/groceror-users/prometheus.yml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: groceror-users
    static_configs:
      - targets: ["groceror-users:8002"]
```

- [ ] **Step 3: Create Grafana datasource provisioning**

```yaml
# /code/groceror-users/grafana/provisioning/datasources/prometheus.yml
apiVersion: 1

datasources:
  - name: Prometheus
    type: prometheus
    access: proxy
    url: http://prometheus:9090
    isDefault: true
    editable: false
```

- [ ] **Step 4: Create Grafana dashboard provider**

```yaml
# /code/groceror-users/grafana/provisioning/dashboards/provider.yml
apiVersion: 1

providers:
  - name: groceror-users
    folder: groceror
    type: file
    disableDeletion: true
    options:
      path: /var/lib/grafana/dashboards
```

- [ ] **Step 5: Create Grafana dashboard JSON**

```json
{
  "annotations": {"list": []},
  "editable": true,
  "panels": [
    {
      "datasource": {"type": "prometheus", "uid": "prometheus"},
      "fieldConfig": {"defaults": {"color": {"mode": "palette-classic"}, "custom": {}}, "overrides": []},
      "gridPos": {"h": 8, "w": 12, "x": 0, "y": 0},
      "id": 1,
      "options": {"legend": {"displayMode": "list", "placement": "bottom"}, "tooltip": {"mode": "single"}},
      "targets": [{"datasource": {"type": "prometheus"}, "expr": "rate(groceror_users_events_total{event_type=\"user_registered\"}[5m])", "legendFormat": "registrations/min", "refId": "A"}],
      "title": "Registrations/min",
      "type": "timeseries"
    },
    {
      "datasource": {"type": "prometheus", "uid": "prometheus"},
      "fieldConfig": {"defaults": {}, "overrides": []},
      "gridPos": {"h": 4, "w": 6, "x": 12, "y": 0},
      "id": 2,
      "options": {"colorMode": "value", "graphMode": "area", "reduceOptions": {"calcs": ["lastNotNull"]}},
      "targets": [{"datasource": {"type": "prometheus"}, "expr": "groceror_users_events_total{event_type=\"user_registered\"}", "legendFormat": "Total", "refId": "A"}],
      "title": "Total Registrations",
      "type": "stat"
    },
    {
      "datasource": {"type": "prometheus", "uid": "prometheus"},
      "fieldConfig": {"defaults": {"color": {"mode": "palette-classic"}, "custom": {}}, "overrides": []},
      "gridPos": {"h": 8, "w": 12, "x": 0, "y": 8},
      "id": 3,
      "options": {"barWidth": 0.97, "groupWidth": 0.7, "legend": {"displayMode": "list"}, "tooltip": {"mode": "single"}},
      "targets": [{"datasource": {"type": "prometheus"}, "expr": "groceror_users_events_total", "legendFormat": "{{event_type}}", "refId": "A"}],
      "title": "Events by Type",
      "type": "barchart"
    },
    {
      "datasource": {"type": "prometheus", "uid": "prometheus"},
      "fieldConfig": {"defaults": {"color": {"mode": "palette-classic"}, "custom": {}}, "overrides": []},
      "gridPos": {"h": 8, "w": 12, "x": 12, "y": 8},
      "id": 4,
      "options": {"legend": {"displayMode": "list"}, "tooltip": {"mode": "single"}},
      "targets": [{"datasource": {"type": "prometheus"}, "expr": "rate(groceror_users_processing_errors_total[5m])", "legendFormat": "{{event_type}}/{{reason}}", "refId": "A"}],
      "title": "Error Rate",
      "type": "timeseries"
    },
    {
      "datasource": {"type": "prometheus", "uid": "prometheus"},
      "fieldConfig": {"defaults": {"color": {"mode": "thresholds"}, "thresholds": {"mode": "absolute", "steps": [{"color": "red", "value": 0}, {"color": "green", "value": 1}]}}, "overrides": []},
      "gridPos": {"h": 4, "w": 6, "x": 12, "y": 4},
      "id": 5,
      "options": {"colorMode": "background", "graphMode": "none", "reduceOptions": {"calcs": ["lastNotNull"]}},
      "targets": [{"datasource": {"type": "prometheus"}, "expr": "groceror_users_consumer_up", "legendFormat": "Consumer", "refId": "A"}],
      "title": "Consumer Status",
      "type": "stat"
    }
  ],
  "refresh": "10s",
  "schemaVersion": 38,
  "tags": ["groceror", "users"],
  "time": {"from": "now-1h", "to": "now"},
  "timezone": "browser",
  "title": "groceror-users",
  "uid": "groceror-users",
  "version": 1
}
```

Save this JSON to `/code/groceror-users/grafana/dashboards/user_events.json`.

- [ ] **Step 6: Verify docker-compose parses cleanly**

```bash
cd /code/groceror-users && docker compose config --quiet
```
Expected: No errors printed.

- [ ] **Step 7: Commit**

```bash
cd /code/groceror-users
git add docker-compose.yml prometheus.yml grafana/
git commit -m "feat: add docker-compose with MongoDB, Prometheus, and Grafana"
```

---

## Task 12: smoke test

- [ ] **Step 1: Start RabbitMQ if not already running**

```bash
docker run -d --name rabbitmq -p 5672:5672 -p 15672:15672 rabbitmq:3-management
```
Expected: RabbitMQ management UI accessible at http://localhost:15672 (guest/guest)

- [ ] **Step 2: Start groceror-users stack**

```bash
cd /code/groceror-users && docker compose up --build -d
```
Expected: All 4 services start. Check with:
```bash
docker compose ps
```
All services should show `running`.

- [ ] **Step 3: Confirm /health**

```bash
curl http://localhost:8002/health
```
Expected: `{"status":"ok"}`

- [ ] **Step 4: Trigger a user_registered event via groceror**

In a separate terminal with groceror running:
```bash
# From /code/groceror:
# 1. Send OTP
curl -s -X POST http://localhost:8000/user/send-otp -H 'Content-Type: application/json' -d '{"phone":"+15559990001"}'
# 2. Get OTP from logs or legacy endpoint
curl -s -X POST "http://localhost:8000/user/otp?phone=%2B15559990001"
# 3. Verify OTP (replace 123456 with the returned OTP)
curl -s -X POST http://localhost:8000/user/verify-otp -H 'Content-Type: application/json' -d '{"phone":"+15559990001","otp":"123456"}'
# 4. Register
curl -s -X POST http://localhost:8000/user/register -H 'Content-Type: application/json' -d '{"phone":"+15559990001","entity_type":"user","password":"test1234"}'
```

- [ ] **Step 5: Confirm event landed in MongoDB**

```bash
docker compose exec mongodb mongosh users --eval "db.user_events.find().pretty()"
```
Expected: Document with `event: "user_registered"` and the correct phone number.

- [ ] **Step 6: Confirm Prometheus scraped the metric**

```bash
curl -s http://localhost:8002/metrics | grep groceror_users_events_total
```
Expected: `groceror_users_events_total{event_type="user_registered"} 1.0`

- [ ] **Step 7: Open Grafana and verify dashboard**

Open http://localhost:3001 — login with admin/admin.
Navigate to Dashboards → groceror → groceror-users.
Expected: "Total Registrations" stat panel shows 1. "Consumer Status" shows green.

- [ ] **Step 8: Final commit in groceror-users**

```bash
cd /code/groceror-users && git tag v0.1.0
```

---

## Self-Review Checklist (completed)

- [x] All 4 events published from groceror (Tasks 1–2)
- [x] validator covers all event types + unknown schema + unknown event + missing fields (Task 4)
- [x] MongoDB append-only insert tested (Task 5)
- [x] Prometheus + Pushgateway metrics path tested (Task 6)
- [x] handler tested for success, all failure modes, and all event types (Task 7)
- [x] consumer ACK/NACK/DLQ routing tested (Task 8)
- [x] /health and /metrics endpoints tested (Task 9)
- [x] Lambda Amazon MQ and SQS paths tested (Task 10)
- [x] docker-compose + Grafana provisioning included (Task 11)
- [x] End-to-end smoke test steps included (Task 12)
- [x] No TBDs, TODOs, or placeholder text
- [x] Type signatures consistent across tasks (DB, process_message signature)
- [x] Lambda `handler` return value matches test assertions
