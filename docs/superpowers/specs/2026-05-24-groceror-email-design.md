# Design: groceror-email microservice

**Status:** Approved  
**Date:** 2026-05-24  
**Author:** Engineering  
**Services affected:** `groceror` (topology change), `groceror-email` (rewrite)

---

## 1. Background & Goal

`groceror-email` is an existing stub microservice (`main.py` + `send_email.py`) built on Flask that consumes from `email_queue` and sends SMTP emails. It lacks DLQ routing, Prometheus metrics, Grafana dashboarding, Docker infrastructure, Lambda support, tests, and consistency with the FastAPI pattern used by `groceror-users` and `groceror-orders`.

**Goal:** Rewrite `groceror-email` as a FastAPI microservice following the same patterns as `groceror-users` and `groceror-orders` — pika consumer thread, pure handler function, Prometheus metrics, Grafana dashboard, Docker Compose, and Lambda compatibility. The service is a generic email relay: any service publishes `{recipient, subject, body}` to `email_queue` and groceror-email delivers it via SMTP.

---

## 2. Architecture

```
groceror / groceror-users / groceror-orders
  └─ client.py  →  RabbitMQ: email_queue (durable)
                                    │           email_queue.dlq (DLQ)
                             groceror-email
                               ├─ [thread] pika consumer
                               │     └─ validate → send SMTP → emit metric
                               └─ [main]  FastAPI
                                     ├─ GET /metrics  (Prometheus)
                                     └─ GET /health
                                            │
                                       Prometheus ──► Grafana
```

groceror-email runs as a single process with two threads (mirrors groceror-users and groceror-orders):
- **Background thread:** pika blocking consumer with reconnect loop
- **Main thread:** FastAPI serving `/metrics` and `/health`

No database — groceror-email is a stateless relay. The RabbitMQ instance is shared with groceror. groceror-email does not run its own broker.

---

## 3. File Structure

```
/code/groceror-email/
├── main.py              # entry point: starts consumer thread, runs FastAPI
├── consumer.py          # pika reconnect loop, calls handler.process_message()
├── handler.py           # pure function: validate → send email → emit metric
├── lambda_handler.py    # AWS Lambda entry point (Amazon MQ + SQS triggers)
├── validator.py         # Pydantic model for email message envelope
├── mailer.py            # SMTP sending via smtplib
├── metrics.py           # Prometheus counters + consumer_up gauge
├── api.py               # FastAPI: GET /health + GET /metrics
├── config.py            # all env vars
├── client.py            # publisher client (replaces send_email.py)
├── requirements.txt
├── requirements-dev.txt
├── Dockerfile
├── docker-compose.yml   # groceror-email + Prometheus + Grafana
├── prometheus.yml
└── grafana/
    ├── provisioning/
    │   ├── datasources/prometheus.yml
    │   └── dashboards/provider.yml
    └── dashboards/email_events.json
```

### groceror change (one file)

- `engine/publisher.py` — add `email_queue` + `email_queue.dlq` to `_declare_topology()`

---

## 4. Message Contract

All messages use the groceror envelope format:

```json
{
  "schema_version": "1.0",
  "event": "send_email",
  "recipient": "user@example.com",
  "subject": "Welcome to groceror",
  "body": "Plain text email body"
}
```

All four fields are required. `client.py` builds the envelope so callers use:

```python
from client import EmailClient

EmailClient().send(
    recipient="user@example.com",
    subject="Welcome to groceror",
    body="Hello, your account is ready."
)
```

---

## 5. RabbitMQ Topology

| Resource | Value |
|---|---|
| Queue | `email_queue`, durable=True |
| Dead-letter exchange | `dlx` (shared, already declared by groceror publisher) |
| Dead-letter routing key | `email_queue` |
| DLQ | `email_queue.dlq`, durable=True |
| Prefetch count | 1 |
| Heartbeat | 600s |

groceror-email declares its own queue and DLQ on startup. The `dlx` exchange declaration is idempotent.

---

## 6. handler.py

Pure function with no transport dependency:

```python
def process_message(raw: dict, mailer: Mailer, metrics: MetricsEmitter) -> None:
    # validate → send email → emit metric
```

**Container:** `consumer.py` deserialises the pika message body and calls `handler.process_message()`.

**Lambda:** `lambda_handler.py` unwraps the Amazon MQ or SQS event envelope and calls `handler.process_message()`.

---

## 7. mailer.py

Sends email via `smtplib` using STARTTLS:

```python
class Mailer:
    def send(self, recipient: str, subject: str, body: str) -> None:
        # raises SMTPException on failure
```

Raises on failure so `handler.py` can catch it and emit the correct error metric.

---

## 8. Prometheus Metrics

| Metric | Type | Labels | Description |
|---|---|---|---|
| `groceror_email_sent_total` | Counter | `status` (`success`/`failure`) | Emails attempted |
| `groceror_email_processing_errors_total` | Counter | `reason` | Validation or SMTP errors |
| `groceror_email_consumer_up` | Gauge | — | `1` when connected, `0` otherwise |

`metrics.py` checks `METRICS_BACKEND` env var:
- `prometheus` (default): in-process counters scraped at `/metrics`
- `pushgateway`: calls `push_to_gateway()` after each message (Lambda deployment)

---

## 9. Error Handling

| Failure scenario | Behaviour |
|---|---|
| RabbitMQ unreachable at startup | Reconnect loop with 5s backoff |
| Invalid JSON | NACK `requeue=False` → DLQ; `errors_total{reason="validation"}` |
| Pydantic validation failure | NACK `requeue=False` → DLQ; `errors_total{reason="validation"}` |
| SMTP failure, first delivery | NACK `requeue=True` — retry once |
| SMTP failure, redelivered=True | NACK `requeue=False` → DLQ; `errors_total{reason="smtp"}` |
| Consumer thread crashes | `consumer_up` set to 0; FastAPI stays alive |
| Lambda invocation failure | Lambda retries per configured retry policy |

---

## 10. Deployment

**docker-compose services:**

| Service | Image | Port | Notes |
|---|---|---|---|
| `groceror-email` | local build | 8003 | FastAPI + pika consumer |
| `prometheus` | prom/prometheus | 9092 | Scrapes groceror-email:8003/metrics |
| `grafana` | grafana/grafana | 3003 | Provisioned datasource + dashboard |

No database service — groceror-email is stateless.

**Environment variables:**

```
RABBITMQ_HOST=localhost
RABBITMQ_PORT=5672
RABBITMQ_USER=guest
RABBITMQ_PASS=guest
RABBITMQ_VHOST=/
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USERNAME=your@gmail.com
MAIL_PASSWORD=your-app-password
MAIL_FROM=your@gmail.com
API_HOST=0.0.0.0
API_PORT=8003
METRICS_BACKEND=prometheus
PUSHGATEWAY_URL=
```

---

## 11. Grafana Dashboard

Provisioned automatically from `grafana/dashboards/email_events.json`.

| Panel | Type | Query |
|---|---|---|
| Emails sent/min | Time series | `rate(groceror_email_sent_total{status="success"}[5m])` |
| Total emails sent | Stat | `groceror_email_sent_total{status="success"}` |
| Error rate | Time series | `rate(groceror_email_processing_errors_total[5m])` |
| Consumer status | Stat (green/red) | `groceror_email_consumer_up` |

---

## 12. Out of Scope

- HTML email templates (plain text only, first iteration)
- Email open/click tracking
- Per-recipient send history
- Multiple SMTP providers or failover
- Authentication on `/metrics` or `/health`
