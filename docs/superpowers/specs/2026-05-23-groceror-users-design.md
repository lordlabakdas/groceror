# Design: groceror-users microservice

**Status:** Approved  
**Date:** 2026-05-23  
**Author:** Engineering  
**Services affected:** `groceror` (producer), `groceror-users` (new consumer)

---

## 1. Background & Goal

`groceror` is a FastAPI + PostgreSQL platform for grocery stores. It manages user registration via OTP, profile setup, and password management. Currently, user lifecycle events are not published to any message broker — the publish call in `user_api.py` is commented out.

`groceror-users` is a new Python microservice that consumes user lifecycle events from RabbitMQ, stores them as an immutable event log in MongoDB, and exposes Prometheus metrics scraped by Grafana for dashboarding.

**Goal:** Wire up the commented-out user event publishing in groceror, build groceror-users as an event consumer with MongoDB storage and Grafana observability, and design the core logic to be deployable as either a long-running container or an AWS Lambda function.

---

## 2. Events

Four user lifecycle events are published by groceror and consumed by groceror-users:

| Event | Published from | Trigger |
|---|---|---|
| `user_registered` | `api/user_api.py` `POST /user/register` | PhoneVerification record updated with entity_type + password |
| `otp_verified` | `api/user_api.py` `POST /user/verify-otp` | OTP successfully verified |
| `profile_updated` | `api/user_api.py` `POST /user/set-profile` | User or Store profile created/updated |
| `password_changed` | `api/user_api.py` `PUT /user/change-password` | Password successfully changed |

---

## 3. Architecture

```
groceror (FastAPI)
  ├─ POST /user/register        → publishes user_registered      ─┐
  ├─ POST /user/verify-otp      → publishes otp_verified          │  RabbitMQ
  ├─ POST /user/set-profile     → publishes profile_updated       │  user_events_queue (durable)
  └─ PUT  /user/change-password → publishes password_changed     ─┘  user_events_queue.dlq (DLQ)
                                                                   │
                                                          groceror-users
                                                            ├─ [thread] pika consumer
                                                            │     └─ validate → save → emit metric
                                                            └─ [main]  FastAPI
                                                                  ├─ GET /metrics  (Prometheus)
                                                                  └─ GET /health
                                                                   │
                                                                MongoDB
                                                                db: users / collection: user_events
                                                                   │
                                                                Prometheus ──► Grafana
```

groceror-users runs as a single process with two threads (mirrors groceror-orders):
- **Background thread:** pika blocking consumer with reconnect loop
- **Main thread:** FastAPI serving `/metrics` and `/health`

The RabbitMQ instance is **shared** with groceror — groceror-users connects to the same broker via `RABBITMQ_HOST`. groceror-users does not run its own RabbitMQ.

---

## 4. File Structure

```
/code/groceror-users/
├── main.py              # entry point: starts consumer thread, runs FastAPI
├── consumer.py          # pika setup, reconnect loop, calls handler.process_message()
├── handler.py           # pure function: validate → save → emit metric (no transport coupling)
├── lambda_handler.py    # AWS Lambda entry point: unwraps Amazon MQ/SQS event → calls handler
├── validator.py         # Pydantic models for all 4 event types + shared envelope
├── db.py                # MongoDB client, append-only insert
├── metrics.py           # metric emission: Prometheus in-process (container) or Pushgateway (Lambda)
├── api.py               # FastAPI app: GET /metrics + GET /health
├── config.py            # all configuration from environment variables
├── requirements.txt
├── docker-compose.yml   # groceror-users + MongoDB + Prometheus + Grafana
├── prometheus.yml       # scrape config → groceror-users:8002/metrics
└── grafana/
    └── dashboards/
        └── user_events.json  # provisioned Grafana dashboard
```

### groceror changes (two files)

- `engine/publisher.py` — add `user_events_queue` + `user_events_queue.dlq` to declared topology
- `api/user_api.py` — uncomment + wire the 4 publish calls

---

## 5. Message Contract

All messages use the existing groceror envelope format from `engine/publisher.py`:

```json
{
  "schema_version": "1.0",
  "event": "<event_name>",
  ...event-specific fields...
}
```

### 5.1 user_registered

```json
{
  "schema_version": "1.0",
  "event": "user_registered",
  "user_id": "<PhoneVerification.id>",
  "phone": "+1234567890",
  "entity_type": "user|store"
}
```

### 5.2 otp_verified

```json
{
  "schema_version": "1.0",
  "event": "otp_verified",
  "user_id": "<PhoneVerification.id>",
  "phone": "+1234567890"
}
```

### 5.3 profile_updated

```json
{
  "schema_version": "1.0",
  "event": "profile_updated",
  "user_id": "<PhoneVerification.id>",
  "profile_id": "<User.id|Store.id>",
  "entity_type": "user|store",
  "name": "...",
  "email": "...",
  "location": "..."
}
```

### 5.4 password_changed

```json
{
  "schema_version": "1.0",
  "event": "password_changed",
  "user_id": "<PhoneVerification.id>",
  "phone": "+1234567890"
}
```

---

## 6. MongoDB Document Model

**Database:** `users`  
**Collection:** `user_events`  
**Strategy:** Append-only — documents are inserted, never updated.

```json
{
  "_id":            "<ObjectId>",
  "event":          "user_registered",
  "schema_version": "1.0",
  "user_id":        "6ba7b810-...",
  "phone":          "+1234567890",
  "entity_type":    "user",
  "received_at":    "2026-05-23T10:00:01Z",
  "raw_payload":    { "...full original message..." }
}
```

- `received_at` is stamped by groceror-users at consumption time, not by the producer.
- `raw_payload` preserves the complete original message for future replay.
- Index on `(user_id, event)` for per-user event history queries.
- No deduplication — replayed messages are valid additional history entries.

---

## 7. Prometheus Metrics

| Metric | Type | Labels | Description |
|---|---|---|---|
| `groceror_users_events_total` | Counter | `event_type` | Incremented on each successfully stored event |
| `groceror_users_processing_errors_total` | Counter | `event_type`, `reason` | Incremented on validation, DB, or schema errors |
| `groceror_users_consumer_up` | Gauge | — | 1 when pika consumer is connected, 0 otherwise |

`metrics.py` checks `METRICS_BACKEND` env var:
- `prometheus` (default): standard in-process `prometheus_client` counters, scraped at `/metrics`
- `pushgateway`: calls `push_to_gateway()` after each message batch (Lambda deployment)

---

## 8. Lambda Compatibility

`handler.py` is a pure function with no transport dependency:

```python
def process_message(raw: dict, db: DB, metrics: MetricsEmitter) -> None:
    # validate → save → emit metric
```

**Container:** `consumer.py` deserialises the pika message body and calls `handler.process_message()`.

**Lambda:** `lambda_handler.py` unwraps the Amazon MQ or SQS event envelope, extracts the message body, and calls `handler.process_message()`. Uses `METRICS_BACKEND=pushgateway`.

No shared state between the two entry points. DB and metrics objects are constructed at startup (container) or per invocation (Lambda).

---

## 9. RabbitMQ Topology

| Resource | Value |
|---|---|
| Queue | `user_events_queue`, durable=True |
| Dead-letter exchange | `dlx` (shared, already declared by groceror publisher) |
| Dead-letter routing key | `user_events_queue` |
| DLQ | `user_events_queue.dlq`, durable=True |
| Prefetch count | 1 |
| Heartbeat | 600s |

groceror-users declares its own queue and DLQ on startup. Both groceror and groceror-users call `exchange_declare(exchange="dlx", exchange_type="direct", durable=True)` — RabbitMQ treats this as idempotent when arguments are identical, so declaration order does not matter.

---

## 10. Error Handling

| Failure scenario | Behaviour |
|---|---|
| RabbitMQ unreachable at startup | Reconnect loop with 5s backoff |
| Message fails Pydantic validation | NACK `requeue=False` → DLQ; `errors_total{reason="validation"}` incremented |
| Unknown `schema_version` | NACK `requeue=False` → DLQ; `errors_total{reason="unknown_schema"}` incremented |
| MongoDB write fails | First delivery: NACK `requeue=True`. If `redelivered=True` on second attempt: NACK `requeue=False` → DLQ; `errors_total{reason="db"}` incremented |
| Consumer thread crashes | `consumer_up` gauge set to 0; FastAPI main thread stays alive, `/metrics` and `/health` remain reachable |
| Lambda invocation failure | Lambda retries per configured retry policy; Pushgateway push is best-effort (logged, not fatal) |
| groceror publish fails | groceror logs warning, returns HTTP 200 — user action succeeded. No backfill. |

---

## 11. Deployment

**docker-compose services:**

| Service | Image | Port | Notes |
|---|---|---|---|
| `groceror-users` | local build | 8002 | FastAPI + pika consumer |
| `mongodb` | mongo:7 | 27018 | Separate from groceror-orders (27017) |
| `prometheus` | prom/prometheus | 9090 | Scrapes groceror-users:8002/metrics |
| `grafana` | grafana/grafana | 3001 | Provisioned datasource + dashboard |

**Environment variables:**

```
RABBITMQ_HOST=localhost
RABBITMQ_PORT=5672
RABBITMQ_USER=guest
RABBITMQ_PASS=guest
RABBITMQ_VHOST=/
MONGO_URI=mongodb://localhost:27018
API_HOST=0.0.0.0
API_PORT=8002
METRICS_BACKEND=prometheus
PUSHGATEWAY_URL=http://localhost:9091
```

---

## 12. Grafana Dashboard

Provisioned automatically from `grafana/dashboards/user_events.json`.

| Panel | Type | Query |
|---|---|---|
| Registrations/min | Time series | `rate(groceror_users_events_total{event_type="user_registered"}[5m])` |
| Total registrations | Stat | `groceror_users_events_total{event_type="user_registered"}` |
| Events by type | Bar chart | `groceror_users_events_total` grouped by `event_type` |
| Error rate | Time series | `rate(groceror_users_processing_errors_total[5m])` |
| Consumer status | Stat (green/red) | `groceror_users_consumer_up` |

---

## 13. Out of Scope

- Authentication on `/metrics` or `/health` (internal service, first iteration)
- Historical backfill of existing groceror users into MongoDB
- Per-user event history API endpoint
- SMS delivery event tracking (OTP send confirmations)
- Topic exchange migration (can be layered on later as a groceror-side change)
- Kubernetes manifests
