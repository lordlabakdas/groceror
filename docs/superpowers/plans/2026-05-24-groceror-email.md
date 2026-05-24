# groceror-email Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewrite groceror-email as a FastAPI microservice matching the groceror-users/groceror-orders pattern — pika consumer, pure handler, Prometheus metrics, Grafana dashboard, Docker Compose, and Lambda support.

**Architecture:** A background pika thread consumes `email_queue`, validates each message, and sends SMTP email via `smtplib`. A FastAPI main thread serves `/health` and `/metrics`. No database — purely stateless relay. groceror's `engine/publisher.py` is extended with `email_queue` topology so the shared DLQ infrastructure covers email too.

**Tech Stack:** Python 3.11, FastAPI, uvicorn, pika, smtplib, pydantic v2, prometheus-client, pytest, mongomock (not needed — no DB), Docker Compose

---

## File map

| File | Action | Responsibility |
|---|---|---|
| `config.py` | Create | All env vars + queue constants |
| `validator.py` | Create | Pydantic `EmailMessage` model + `parse_message()` |
| `mailer.py` | Create | SMTP send via smtplib |
| `metrics.py` | Create | `groceror_email_*` counters + gauge |
| `handler.py` | Create | Pure fn: validate → send → emit metric |
| `consumer.py` | Create | pika reconnect loop + ACK/NACK routing |
| `api.py` | Create | FastAPI `/health` + `/metrics` |
| `client.py` | Create | Publisher helper (replaces `send_email.py`) |
| `main.py` | Replace | Entry point: consumer thread + uvicorn |
| `lambda_handler.py` | Create | AWS Lambda entry point |
| `requirements.txt` | Replace | Pinned production deps |
| `requirements-dev.txt` | Create | Test deps |
| `Dockerfile` | Create | python:3.11-slim image |
| `docker-compose.yml` | Create | app + Prometheus (9092) + Grafana (3003) |
| `prometheus.yml` | Create | Scrape config |
| `grafana/provisioning/datasources/prometheus.yml` | Create | Prometheus datasource uid=prometheus |
| `grafana/provisioning/dashboards/provider.yml` | Create | Dashboard file provider |
| `grafana/dashboards/email_events.json` | Create | 4-panel dashboard |
| `send_email.py` | Delete | Replaced by `client.py` |
| `/code/groceror/engine/publisher.py` | Modify | Add `email_queue` + `email_queue.dlq` topology |
| `/code/groceror/tests/unit/test_publisher_topology.py` | Modify | Add email queue topology tests |

Work directory: `/code/groceror-email/`

---

## Task 1: groceror — extend publisher topology for email_queue

**Files:**
- Modify: `/code/groceror/engine/publisher.py`
- Modify: `/code/groceror/tests/unit/test_publisher_topology.py`

- [ ] **Step 1: Write failing tests**

Open `/code/groceror/tests/unit/test_publisher_topology.py` and add at the end:

```python
def test_email_dlq_declared():
    ch = MagicMock()
    _declare_topology(ch)
    queue_calls = {call.kwargs["queue"]: call.kwargs for call in ch.queue_declare.call_args_list}
    assert "email_queue.dlq" in queue_calls
    assert queue_calls["email_queue.dlq"].get("durable") is True


def test_email_dlq_bound_to_dlx():
    ch = MagicMock()
    _declare_topology(ch)
    bind_calls = {call.kwargs["queue"]: call.kwargs for call in ch.queue_bind.call_args_list}
    assert "email_queue.dlq" in bind_calls
    assert bind_calls["email_queue.dlq"]["exchange"] == "dlx"
    assert bind_calls["email_queue.dlq"]["routing_key"] == "email_queue"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /code/groceror
source venv/bin/activate
pytest tests/unit/test_publisher_topology.py -v
```

Expected: 2 new tests FAIL with `AssertionError`.

- [ ] **Step 3: Add email queue constants and topology to publisher.py**

Open `/code/groceror/engine/publisher.py`. Add after `USER_EVENTS_DLQ`:

```python
EMAIL_QUEUE = "email_queue"
EMAIL_DLQ   = "email_queue.dlq"
```

In `_declare_topology`, add after the user events DLQ block:

```python
    # email events DLQ
    channel.queue_declare(queue=EMAIL_DLQ, durable=True)
    channel.queue_bind(exchange=DLX_EXCHANGE, queue=EMAIL_DLQ, routing_key=EMAIL_QUEUE)
```

Update the module docstring to mention `email_queue.dlq`:

```python
"""
RabbitMQ publisher for groceror.
...
Dead-letter exchange (``dlx``) and dead-letter queues (``order_queue.dlq``,
``user_events_queue.dlq``, ``email_queue.dlq``) are declared on first use so
that NACKed or expired messages are never silently dropped.
"""
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/unit/test_publisher_topology.py -v
```

Expected: all topology tests PASS.

- [ ] **Step 5: Commit**

```bash
git add engine/publisher.py tests/unit/test_publisher_topology.py
git commit -m "feat: add email_queue DLQ to publisher topology"
```

---

## Task 2: groceror-email — project scaffold

**Files:**
- Create: `config.py`
- Replace: `requirements.txt`
- Create: `requirements-dev.txt`
- Create: `Dockerfile`
- Delete: `send_email.py`

- [ ] **Step 1: Delete the old stub files**

```bash
cd /code/groceror-email
rm send_email.py
```

Do NOT delete `main.py` yet — it will be replaced in Task 10.

- [ ] **Step 2: Create config.py**

```python
import os

RABBITMQ_HOST   = os.getenv("RABBITMQ_HOST", "localhost")
RABBITMQ_PORT   = int(os.getenv("RABBITMQ_PORT", 5672))
RABBITMQ_USER   = os.getenv("RABBITMQ_USER", "guest")
RABBITMQ_PASS   = os.getenv("RABBITMQ_PASS", "guest")
RABBITMQ_VHOST  = os.getenv("RABBITMQ_VHOST", "/")

MAIL_SERVER   = os.getenv("MAIL_SERVER", "smtp.gmail.com")
MAIL_PORT     = int(os.getenv("MAIL_PORT", 587))
MAIL_USERNAME = os.getenv("MAIL_USERNAME", "")
MAIL_PASSWORD = os.getenv("MAIL_PASSWORD", "")
MAIL_FROM     = os.getenv("MAIL_FROM", MAIL_USERNAME)

API_HOST = os.getenv("API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("API_PORT", 8003))

METRICS_BACKEND = os.getenv("METRICS_BACKEND", "prometheus")
PUSHGATEWAY_URL = os.getenv("PUSHGATEWAY_URL", "")

QUEUE_NAME   = "email_queue"
DLQ_NAME     = "email_queue.dlq"
DLX_EXCHANGE = "dlx"
```

- [ ] **Step 3: Replace requirements.txt**

```
fastapi>=0.111.0
uvicorn[standard]>=0.29.0
pika>=1.3.2
prometheus-client>=0.20.0
pydantic>=2.7.0
```

- [ ] **Step 4: Create requirements-dev.txt**

```
pytest>=7.4
pytest-asyncio>=0.23
httpx>=0.27
pytest-mock>=3.14.0
```

- [ ] **Step 5: Create Dockerfile**

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["python", "main.py"]
```

- [ ] **Step 6: Install deps into venv**

```bash
source venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
```

- [ ] **Step 7: Commit**

```bash
git add config.py requirements.txt requirements-dev.txt Dockerfile
git rm send_email.py
git commit -m "feat: scaffold groceror-email — config, requirements, Dockerfile"
```

---

## Task 3: groceror-email — validator

**Files:**
- Create: `validator.py`
- Create: `tests/test_validator.py`

- [ ] **Step 1: Write failing tests**

Create `tests/__init__.py` (empty) and `tests/test_validator.py`:

```python
import pytest
from pydantic import ValidationError

from validator import parse_message, EmailMessage


VALID = {
    "schema_version": "1.0",
    "event": "send_email",
    "recipient": "user@example.com",
    "subject": "Hello",
    "body": "Test body",
}


def test_parse_valid_message():
    msg = parse_message(VALID)
    assert isinstance(msg, EmailMessage)
    assert msg.recipient == "user@example.com"
    assert msg.subject == "Hello"
    assert msg.body == "Test body"


def test_unknown_schema_version_raises():
    bad = {**VALID, "schema_version": "9.9"}
    with pytest.raises(ValueError, match="schema_version"):
        parse_message(bad)


def test_unknown_event_raises():
    bad = {**VALID, "event": "not_send_email"}
    with pytest.raises(ValueError, match="event"):
        parse_message(bad)


def test_missing_recipient_raises():
    bad = {k: v for k, v in VALID.items() if k != "recipient"}
    with pytest.raises(ValidationError):
        parse_message(bad)


def test_missing_subject_raises():
    bad = {k: v for k, v in VALID.items() if k != "subject"}
    with pytest.raises(ValidationError):
        parse_message(bad)


def test_missing_body_raises():
    bad = {k: v for k, v in VALID.items() if k != "body"}
    with pytest.raises(ValidationError):
        parse_message(bad)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_validator.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'validator'`.

- [ ] **Step 3: Create validator.py**

```python
from typing import Literal

from pydantic import BaseModel

SUPPORTED_SCHEMA_VERSIONS = {"1.0"}


class EmailMessage(BaseModel):
    schema_version: str = "1.0"
    event: Literal["send_email"]
    recipient: str
    subject: str
    body: str


def parse_message(data: dict) -> EmailMessage:
    """Validate an email message dict and return a typed model instance.

    Raises:
        ValueError: unknown schema_version or event type
        pydantic.ValidationError: payload does not match the model
    """
    version = data.get("schema_version")
    if version not in SUPPORTED_SCHEMA_VERSIONS:
        raise ValueError(f"Unsupported schema_version: {version!r}")

    if data.get("event") != "send_email":
        raise ValueError(f"Unknown event type: {data.get('event')!r}")

    return EmailMessage(**data)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_validator.py -v
```

Expected: 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add validator.py tests/
git commit -m "feat: add email message validator"
```

---

## Task 4: groceror-email — mailer

**Files:**
- Create: `mailer.py`
- Create: `tests/test_mailer.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_mailer.py`:

```python
import smtplib
from unittest.mock import patch, MagicMock

import pytest

from mailer import Mailer


def test_send_connects_to_configured_smtp_server():
    with patch("mailer.smtplib.SMTP") as mock_smtp_cls:
        mock_smtp = MagicMock()
        mock_smtp_cls.return_value.__enter__ = MagicMock(return_value=mock_smtp)
        mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=False)

        mailer = Mailer()
        mailer.send("to@example.com", "Subject", "Body")

        mock_smtp.starttls.assert_called_once()
        mock_smtp.login.assert_called_once()
        mock_smtp.sendmail.assert_called_once()


def test_send_raises_on_smtp_error():
    with patch("mailer.smtplib.SMTP") as mock_smtp_cls:
        mock_smtp = MagicMock()
        mock_smtp.sendmail.side_effect = smtplib.SMTPException("send failed")
        mock_smtp_cls.return_value.__enter__ = MagicMock(return_value=mock_smtp)
        mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=False)

        mailer = Mailer()
        with pytest.raises(smtplib.SMTPException):
            mailer.send("to@example.com", "Subject", "Body")


def test_send_uses_correct_recipient():
    with patch("mailer.smtplib.SMTP") as mock_smtp_cls:
        mock_smtp = MagicMock()
        mock_smtp_cls.return_value.__enter__ = MagicMock(return_value=mock_smtp)
        mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=False)

        mailer = Mailer()
        mailer.send("recipient@example.com", "Subject", "Body")

        call_args = mock_smtp.sendmail.call_args
        assert "recipient@example.com" in call_args[0][1]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_mailer.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'mailer'`.

- [ ] **Step 3: Create mailer.py**

```python
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import config

log = logging.getLogger(__name__)


class Mailer:
    def send(self, recipient: str, subject: str, body: str) -> None:
        """Send a plain-text email via SMTP STARTTLS.

        Raises:
            smtplib.SMTPException: on any SMTP-level failure
        """
        msg = MIMEMultipart()
        msg["From"] = config.MAIL_FROM
        msg["To"] = recipient
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))

        with smtplib.SMTP(config.MAIL_SERVER, config.MAIL_PORT) as smtp:
            smtp.starttls()
            smtp.login(config.MAIL_USERNAME, config.MAIL_PASSWORD)
            smtp.sendmail(config.MAIL_FROM, recipient, msg.as_string())

        log.info("Email sent to %s subject=%r", recipient, subject)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_mailer.py -v
```

Expected: 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add mailer.py tests/test_mailer.py
git commit -m "feat: add smtplib mailer"
```

---

## Task 5: groceror-email — metrics

**Files:**
- Create: `metrics.py`
- Create: `tests/test_metrics.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_metrics.py`:

```python
from unittest.mock import patch, MagicMock

import pytest

import metrics


def test_increment_sent_success_calls_counter():
    with patch.object(metrics.sent_total, "labels") as mock_labels:
        mock_inc = MagicMock()
        mock_labels.return_value.inc = mock_inc
        metrics.increment_sent("success")
    mock_labels.assert_called_once_with(status="success")
    mock_inc.assert_called_once()


def test_increment_sent_failure_calls_counter():
    with patch.object(metrics.sent_total, "labels") as mock_labels:
        mock_inc = MagicMock()
        mock_labels.return_value.inc = mock_inc
        metrics.increment_sent("failure")
    mock_labels.assert_called_once_with(status="failure")
    mock_inc.assert_called_once()


def test_increment_error_calls_counter():
    with patch.object(metrics.processing_errors_total, "labels") as mock_labels:
        mock_inc = MagicMock()
        mock_labels.return_value.inc = mock_inc
        metrics.increment_error("smtp")
    mock_labels.assert_called_once_with(reason="smtp")
    mock_inc.assert_called_once()


def test_set_consumer_status_up():
    with patch.object(metrics.consumer_up, "set") as mock_set:
        metrics.set_consumer_status(True)
    mock_set.assert_called_once_with(1)


def test_set_consumer_status_down():
    with patch.object(metrics.consumer_up, "set") as mock_set:
        metrics.set_consumer_status(False)
    mock_set.assert_called_once_with(0)


def test_pushgateway_not_called_for_prometheus_backend():
    import config
    original = config.METRICS_BACKEND
    config.METRICS_BACKEND = "prometheus"
    try:
        with patch("metrics.push_to_gateway") as mock_push:
            metrics.increment_sent("success")
        mock_push.assert_not_called()
    finally:
        config.METRICS_BACKEND = original


def test_pushgateway_called_when_backend_is_pushgateway():
    import config
    original = config.METRICS_BACKEND
    config.METRICS_BACKEND = "pushgateway"
    try:
        with patch("metrics.push_to_gateway") as mock_push:
            metrics.increment_sent("success")
        mock_push.assert_called_once()
    finally:
        config.METRICS_BACKEND = original
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_metrics.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'metrics'`.

- [ ] **Step 3: Create metrics.py**

```python
import logging

from prometheus_client import Counter, Gauge, push_to_gateway, REGISTRY

import config

log = logging.getLogger(__name__)

sent_total = Counter(
    "groceror_email_sent_total",
    "Total emails attempted",
    ["status"],
)
processing_errors_total = Counter(
    "groceror_email_processing_errors_total",
    "Total email processing errors",
    ["reason"],
)
consumer_up = Gauge(
    "groceror_email_consumer_up",
    "1 when pika consumer is connected, 0 otherwise",
)


def increment_sent(status: str) -> None:
    sent_total.labels(status=status).inc()
    _push_if_needed()


def increment_error(reason: str) -> None:
    processing_errors_total.labels(reason=reason).inc()
    _push_if_needed()


def set_consumer_status(up: bool) -> None:
    consumer_up.set(1 if up else 0)
    _push_if_needed()


def _push_if_needed() -> None:
    if config.METRICS_BACKEND == "pushgateway":
        try:
            push_to_gateway(config.PUSHGATEWAY_URL, job="groceror-email", registry=REGISTRY)
        except Exception as exc:
            log.warning("Pushgateway push failed: %s", exc)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_metrics.py -v
```

Expected: 7 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add metrics.py tests/test_metrics.py
git commit -m "feat: add Prometheus metrics for groceror-email"
```

---

## Task 6: groceror-email — handler

**Files:**
- Create: `handler.py`
- Create: `tests/test_handler.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_handler.py`:

```python
import smtplib
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from handler import process_message


VALID_RAW = {
    "schema_version": "1.0",
    "event": "send_email",
    "recipient": "user@example.com",
    "subject": "Hello",
    "body": "Test body",
}


@pytest.fixture
def mock_mailer():
    return MagicMock()


def test_valid_message_sends_email(mock_mailer):
    with patch("handler.increment_sent") as mock_sent, \
         patch("handler.increment_error") as mock_err:
        process_message(VALID_RAW, mock_mailer)
    mock_mailer.send.assert_called_once_with(
        "user@example.com", "Hello", "Test body"
    )
    mock_sent.assert_called_once_with("success")
    mock_err.assert_not_called()


def test_unknown_schema_raises_and_increments_error(mock_mailer):
    bad = {**VALID_RAW, "schema_version": "9.9"}
    with patch("handler.increment_error") as mock_err:
        with pytest.raises(ValueError):
            process_message(bad, mock_mailer)
    mock_err.assert_called_once_with("validation")
    mock_mailer.send.assert_not_called()


def test_validation_error_raises_and_increments_error(mock_mailer):
    bad = {**VALID_RAW, "recipient": None}
    with patch("handler.increment_error") as mock_err:
        with pytest.raises((ValidationError, ValueError)):
            process_message(bad, mock_mailer)
    mock_err.assert_called_once_with("validation")
    mock_mailer.send.assert_not_called()


def test_smtp_failure_increments_sent_failure_and_smtp_error(mock_mailer):
    mock_mailer.send.side_effect = smtplib.SMTPException("connection refused")
    with patch("handler.increment_sent") as mock_sent, \
         patch("handler.increment_error") as mock_err:
        with pytest.raises(smtplib.SMTPException):
            process_message(VALID_RAW, mock_mailer)
    mock_sent.assert_called_once_with("failure")
    mock_err.assert_called_once_with("smtp")
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_handler.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'handler'`.

- [ ] **Step 3: Create handler.py**

```python
import logging

from pydantic import ValidationError

from mailer import Mailer
from metrics import increment_sent, increment_error
from validator import parse_message

log = logging.getLogger(__name__)


def process_message(raw: dict, mailer: Mailer) -> None:
    """Validate and send one email message.

    Raises:
        ValueError: unknown schema_version or event type
        pydantic.ValidationError: payload does not match the model
        Exception: SMTP failure
    """
    try:
        parsed = parse_message(raw)
    except ValidationError:
        increment_error("validation")
        raise
    except ValueError:
        increment_error("validation")
        raise

    try:
        mailer.send(parsed.recipient, parsed.subject, parsed.body)
    except Exception:
        increment_sent("failure")
        increment_error("smtp")
        raise

    increment_sent("success")
    log.info("Sent email to %s subject=%r", parsed.recipient, parsed.subject)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_handler.py -v
```

Expected: 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add handler.py tests/test_handler.py
git commit -m "feat: add email message handler"
```

---

## Task 7: groceror-email — consumer

**Files:**
- Create: `consumer.py`
- Create: `tests/test_consumer.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_consumer.py`:

```python
import json
from unittest.mock import MagicMock, patch

import pytest
from pydantic import BaseModel, ValidationError

from consumer import _on_message, _declare_topology


def _make_validation_error() -> ValidationError:
    class _M(BaseModel):
        x: int
    try:
        _M(x="not-an-int")
    except ValidationError as exc:
        return exc
    raise AssertionError("Expected ValidationError")


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
def mock_mailer():
    return MagicMock()


VALID_BODY = json.dumps({
    "schema_version": "1.0",
    "event": "send_email",
    "recipient": "u@example.com",
    "subject": "Hi",
    "body": "Body",
}).encode()


def test_valid_message_is_acked(channel, method, mock_mailer):
    with patch("consumer.process_message"):
        _on_message(channel, method, MagicMock(), VALID_BODY, mock_mailer)
    channel.basic_ack.assert_called_once_with(delivery_tag=1)
    channel.basic_nack.assert_not_called()


def test_invalid_json_routes_to_dlq(channel, method, mock_mailer):
    _on_message(channel, method, MagicMock(), b"not-json", mock_mailer)
    channel.basic_nack.assert_called_once_with(delivery_tag=1, requeue=False)
    channel.basic_ack.assert_not_called()


def test_validation_error_routes_to_dlq_on_first_delivery(channel, method, mock_mailer):
    method.redelivered = False
    with patch("consumer.process_message", side_effect=_make_validation_error()):
        _on_message(channel, method, MagicMock(), VALID_BODY, mock_mailer)
    channel.basic_nack.assert_called_once_with(delivery_tag=1, requeue=False)


def test_value_error_routes_to_dlq_on_first_delivery(channel, method, mock_mailer):
    method.redelivered = False
    with patch("consumer.process_message", side_effect=ValueError("bad schema")):
        _on_message(channel, method, MagicMock(), VALID_BODY, mock_mailer)
    channel.basic_nack.assert_called_once_with(delivery_tag=1, requeue=False)


def test_smtp_failure_first_delivery_requeues(channel, method, mock_mailer):
    method.redelivered = False
    with patch("consumer.process_message", side_effect=Exception("smtp down")):
        _on_message(channel, method, MagicMock(), VALID_BODY, mock_mailer)
    channel.basic_nack.assert_called_once_with(delivery_tag=1, requeue=True)


def test_smtp_failure_redelivered_routes_to_dlq(channel, method, mock_mailer):
    method.redelivered = True
    with patch("consumer.process_message", side_effect=Exception("still down")):
        _on_message(channel, method, MagicMock(), VALID_BODY, mock_mailer)
    channel.basic_nack.assert_called_once_with(delivery_tag=1, requeue=False)


def test_declare_topology_creates_email_queue_and_dlq(channel):
    _declare_topology(channel)
    queue_names = [
        c.args[0] if c.args else c.kwargs.get("queue")
        for c in channel.queue_declare.call_args_list
    ]
    assert "email_queue" in queue_names
    assert "email_queue.dlq" in queue_names
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_consumer.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'consumer'`.

- [ ] **Step 3: Create consumer.py**

```python
import json
import logging
import time

import pika
from pydantic import ValidationError

import config
from handler import process_message
from mailer import Mailer
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


def _on_message(channel, method, properties, body: bytes, mailer: Mailer) -> None:
    try:
        raw = json.loads(body)
    except json.JSONDecodeError:
        log.error("Invalid JSON body, routing to DLQ")
        channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
        return

    try:
        process_message(raw, mailer)
        channel.basic_ack(delivery_tag=method.delivery_tag)
    except (ValidationError, ValueError) as exc:
        log.error("Validation/schema error, routing to DLQ: %s", exc)
        channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
    except Exception as exc:
        if method.redelivered:
            log.error("Redelivered message still failing, routing to DLQ: %s", exc)
            channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
        else:
            log.warning("SMTP failure, requeueing once: %s", exc)
            channel.basic_nack(delivery_tag=method.delivery_tag, requeue=True)


def start(mailer: Mailer) -> None:
    """Blocking consumer loop with reconnect-on-failure. Runs forever."""
    while True:
        connection = None
        try:
            connection = _setup_connection()
            channel = connection.channel()
            _declare_topology(channel)
            channel.basic_qos(prefetch_count=1)
            set_consumer_status(True)
            log.info("groceror-email consumer started, waiting for messages...")
            channel.basic_consume(
                queue=config.QUEUE_NAME,
                on_message_callback=lambda ch, m, p, b: _on_message(ch, m, p, b, mailer),
            )
            channel.start_consuming()
        except pika.exceptions.AMQPConnectionError:
            set_consumer_status(False)
            log.error("Lost RabbitMQ connection. Retrying in 5s...")
        except Exception as exc:
            set_consumer_status(False)
            log.error("Unexpected error: %s. Retrying in 5s...", exc)
        finally:
            if connection is not None:
                try:
                    connection.close()
                except Exception:
                    pass
            time.sleep(5)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_consumer.py -v
```

Expected: 7 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add consumer.py tests/test_consumer.py
git commit -m "feat: add pika consumer with ACK/NACK/DLQ routing"
```

---

## Task 8: groceror-email — api

**Files:**
- Create: `api.py`
- Create: `tests/test_api.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_api.py`:

```python
from fastapi.testclient import TestClient

from api import app

client = TestClient(app)


def test_health_returns_ok():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_metrics_returns_200():
    response = client.get("/metrics")
    assert response.status_code == 200


def test_metrics_content_type_is_prometheus():
    response = client.get("/metrics")
    assert "text/plain" in response.headers["content-type"]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_api.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'api'`.

- [ ] **Step 3: Create api.py**

```python
import metrics  # noqa: F401 — registers prometheus metrics on import
from fastapi import FastAPI
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from starlette.responses import Response

app = FastAPI(title="groceror-email")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/metrics")
def get_metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_api.py -v
```

Expected: 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add api.py tests/test_api.py
git commit -m "feat: add FastAPI app with /health and /metrics endpoints"
```

---

## Task 9: groceror-email — client

**Files:**
- Create: `client.py`
- Create: `tests/test_client.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_client.py`:

```python
import json
from unittest.mock import MagicMock, patch

from client import EmailClient


def test_send_publishes_correct_envelope():
    with patch("client.pika.BlockingConnection") as mock_conn_cls:
        mock_channel = MagicMock()
        mock_conn_cls.return_value.channel.return_value = mock_channel

        EmailClient().send(
            recipient="r@example.com",
            subject="Hello",
            body="World",
        )

    mock_channel.basic_publish.assert_called_once()
    body = json.loads(mock_channel.basic_publish.call_args.kwargs["body"])
    assert body["event"] == "send_email"
    assert body["schema_version"] == "1.0"
    assert body["recipient"] == "r@example.com"
    assert body["subject"] == "Hello"
    assert body["body"] == "World"


def test_send_publishes_to_email_queue():
    with patch("client.pika.BlockingConnection") as mock_conn_cls:
        mock_channel = MagicMock()
        mock_conn_cls.return_value.channel.return_value = mock_channel

        EmailClient().send("r@example.com", "S", "B")

    assert mock_channel.basic_publish.call_args.kwargs["routing_key"] == "email_queue"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_client.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'client'`.

- [ ] **Step 3: Create client.py**

```python
import json
import logging

import pika

import config

log = logging.getLogger(__name__)


class EmailClient:
    """Publisher client — any service can use this to queue an email.

    Opens a fresh connection per call (safe for use across threads and
    processes without shared state).
    """

    def send(self, recipient: str, subject: str, body: str) -> None:
        """Queue an email for delivery by groceror-email.

        Raises:
            pika.exceptions.AMQPError: if the broker is unreachable
        """
        message = {
            "schema_version": "1.0",
            "event": "send_email",
            "recipient": recipient,
            "subject": subject,
            "body": body,
        }
        credentials = pika.PlainCredentials(config.RABBITMQ_USER, config.RABBITMQ_PASS)
        params = pika.ConnectionParameters(
            host=config.RABBITMQ_HOST,
            port=config.RABBITMQ_PORT,
            virtual_host=config.RABBITMQ_VHOST,
            credentials=credentials,
        )
        connection = pika.BlockingConnection(params)
        try:
            channel = connection.channel()
            channel.queue_declare(queue=config.QUEUE_NAME, durable=True)
            channel.basic_publish(
                exchange="",
                routing_key=config.QUEUE_NAME,
                body=json.dumps(message),
                properties=pika.BasicProperties(
                    delivery_mode=2,
                    content_type="application/json",
                ),
            )
            log.info("Queued email to %s subject=%r", recipient, subject)
        finally:
            connection.close()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_client.py -v
```

Expected: 2 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add client.py tests/test_client.py
git commit -m "feat: add EmailClient publisher"
```

---

## Task 10: groceror-email — entry points

**Files:**
- Replace: `main.py`
- Create: `lambda_handler.py`

No new tests — these are thin wiring files covered by integration. Verify by running the full test suite.

- [ ] **Step 1: Replace main.py**

```python
import logging
import threading

import uvicorn

import config
from api import app
from consumer import start as start_consumer
from mailer import Mailer

logging.basicConfig(level=logging.INFO)


def main() -> None:
    mailer = Mailer()
    t = threading.Thread(target=start_consumer, args=(mailer,), daemon=True)
    t.start()
    uvicorn.run(app, host=config.API_HOST, port=config.API_PORT, log_level="info")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Create lambda_handler.py**

```python
import base64
import json
import logging

from handler import process_message
from mailer import Mailer

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

_mailer: Mailer | None = None


def _get_mailer() -> Mailer:
    global _mailer
    if _mailer is None:
        _mailer = Mailer()
    return _mailer


def handler(event: dict, context) -> dict:
    """AWS Lambda entry point for Amazon MQ and SQS triggers.

    Amazon MQ event keys:  event["rmqMessagesByQueue"][queue_key][*]["data"] (base64)
    SQS event keys:        event["Records"][*]["body"] (JSON string)
    """
    mailer = _get_mailer()
    failed = 0
    total = 0

    if "rmqMessagesByQueue" in event:
        for messages in event["rmqMessagesByQueue"].values():
            for msg in messages:
                total += 1
                try:
                    body = base64.b64decode(msg["data"]).decode("utf-8")
                    process_message(json.loads(body), mailer)
                except Exception as exc:
                    log.error("Failed to process Amazon MQ message: %s", exc)
                    failed += 1

    elif "Records" in event:
        total = len(event["Records"])
        for record in event["Records"]:
            try:
                process_message(json.loads(record["body"]), mailer)
            except Exception as exc:
                log.error("Failed to process SQS record: %s", exc)
                failed += 1

    return {"processed": total - failed, "failed": failed}
```

- [ ] **Step 3: Run full test suite**

```bash
pytest tests/ -v
```

Expected: all tests PASS.

- [ ] **Step 4: Commit**

```bash
git add main.py lambda_handler.py
git commit -m "feat: add main entry point and Lambda handler"
```

---

## Task 11: groceror-email — docker-compose and Grafana

**Files:**
- Create: `docker-compose.yml`
- Create: `prometheus.yml`
- Create: `grafana/provisioning/datasources/prometheus.yml`
- Create: `grafana/provisioning/dashboards/provider.yml`
- Create: `grafana/dashboards/email_events.json`

No tests — verify with `docker compose config` and JSON parse.

- [ ] **Step 1: Create docker-compose.yml**

```yaml
version: "3.8"

services:
  groceror-email:
    build: .
    ports:
      - "8003:8003"
    environment:
      RABBITMQ_HOST: ${RABBITMQ_HOST:-host.docker.internal}
      RABBITMQ_PORT: ${RABBITMQ_PORT:-5672}
      RABBITMQ_USER: ${RABBITMQ_USER:-guest}
      RABBITMQ_PASS: ${RABBITMQ_PASS:-guest}
      RABBITMQ_VHOST: ${RABBITMQ_VHOST:-/}
      MAIL_SERVER: ${MAIL_SERVER:-smtp.gmail.com}
      MAIL_PORT: ${MAIL_PORT:-587}
      MAIL_USERNAME: ${MAIL_USERNAME:-}
      MAIL_PASSWORD: ${MAIL_PASSWORD:-}
      MAIL_FROM: ${MAIL_FROM:-}
      API_HOST: 0.0.0.0
      API_PORT: 8003
      METRICS_BACKEND: prometheus
      PUSHGATEWAY_URL: ${PUSHGATEWAY_URL:-}
    extra_hosts:
      - "host.docker.internal:host-gateway"

  prometheus:
    image: prom/prometheus:latest
    ports:
      - "9092:9090"
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml:ro

  grafana:
    image: grafana/grafana:latest
    ports:
      - "3003:3000"
    environment:
      GF_SECURITY_ADMIN_USER: admin
      GF_SECURITY_ADMIN_PASSWORD: admin
    volumes:
      - grafana_data:/var/lib/grafana
      - ./grafana/provisioning:/etc/grafana/provisioning:ro
      - ./grafana/dashboards:/var/lib/grafana/dashboards:ro
    depends_on:
      - prometheus

volumes:
  grafana_data:
```

- [ ] **Step 2: Create prometheus.yml**

```yaml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: groceror-email
    static_configs:
      - targets: ["groceror-email:8003"]
```

- [ ] **Step 3: Create grafana/provisioning/datasources/prometheus.yml**

```yaml
apiVersion: 1
datasources:
  - name: Prometheus
    type: prometheus
    uid: prometheus
    url: http://prometheus:9090
    isDefault: true
    access: proxy
```

- [ ] **Step 4: Create grafana/provisioning/dashboards/provider.yml**

```yaml
apiVersion: 1
providers:
  - name: default
    type: file
    options:
      path: /var/lib/grafana/dashboards
```

- [ ] **Step 5: Create grafana/dashboards/email_events.json**

Use `/code/groceror-orders/grafana/dashboards/order_events.json` as the structural template. Adapt it for email metrics:
- Dashboard `uid`: `"email-events-dashboard"`
- Dashboard `title`: `"Email Events"`
- Panel 1 — **Emails/min** — timeseries — `rate(groceror_email_sent_total{status="success"}[5m])`
- Panel 2 — **Total sent** — stat — `groceror_email_sent_total{status="success"}`
- Panel 3 — **Error rate** — timeseries — `rate(groceror_email_processing_errors_total[5m])`
- Panel 4 — **Consumer status** — stat (green threshold=1, red threshold=0) — `groceror_email_consumer_up`

- [ ] **Step 6: Validate YAML and JSON**

```bash
docker compose config > /dev/null && echo "compose OK"
python3 -c "import json; json.load(open('grafana/dashboards/email_events.json')); print('dashboard JSON OK')"
```

Expected: both print OK with no errors.

- [ ] **Step 7: Commit**

```bash
git add docker-compose.yml prometheus.yml grafana/
git commit -m "feat: add docker-compose with Prometheus and Grafana"
```

---

## Task 12: Final wiring — run full test suite and push

- [ ] **Step 1: Run all tests**

```bash
cd /code/groceror-email
source venv/bin/activate
pytest tests/ -v
```

Expected: all tests PASS.

- [ ] **Step 2: Run groceror topology tests**

```bash
cd /code/groceror
source venv/bin/activate
pytest tests/unit/ -v
```

Expected: all tests PASS including the 2 new email topology tests.

- [ ] **Step 3: Push groceror-email**

```bash
cd /code/groceror-email
git push origin master 2>/dev/null || git push origin main
```

- [ ] **Step 4: Push groceror**

```bash
cd /code/groceror
git push origin master
```
