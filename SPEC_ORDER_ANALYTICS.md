# Spec: groceror → groceror-orders Order Analytics Integration

**Status:** Draft  
**Author:** Engineering  
**Services affected:** `groceror` (producer), `groceror-orders` (consumer)

---

## 1. Background & Goal

`groceror` is a FastAPI + PostgreSQL platform for grocery stores. When a customer places an order (`POST /order/create-order`) the order is persisted in PostgreSQL and a message is published to RabbitMQ.

`groceror-orders` is a separate Python service that consumes from RabbitMQ and saves orders to MongoDB. It already contains stub analytics classes (`OrderAnalytics`, `OrderPerDayAnalytics`) but they are not wired up.

**Goal:** Make the two services properly connected end-to-end so that every order placed in `groceror` flows into `groceror-orders`, gets stored in MongoDB, and powers a set of analytics queries that can be exposed over an HTTP API.

---

## 2. Current State

### What already works

| Component | Location | Status |
|---|---|---|
| Order creation & PostgreSQL persistence | `groceror/api/order_api.py` | ✅ Working |
| RabbitMQ publish call | `groceror/engine/publisher.py` | ✅ Works but has gaps (see below) |
| RabbitMQ consumer loop | `groceror-orders/main.py` | ✅ Works but has gaps |
| MongoDB write | `groceror-orders/db.py` | ✅ Working |
| Analytics aggregation stubs | `groceror-orders/analytics/` | ❌ Not wired up |

### Gaps that block a production-ready integration

#### G1 — Message schema mismatch (breaking)

`groceror` publishes `items` as a flat list of UUID strings:
```json
{ "event": "order_created", "items": ["uuid-1", "uuid-2"], ... }
```

`groceror-orders/validator.py` expects:
```python
items: List[Item]   # where Item = {"item": str}
```

The consumer ignores the validator today (it calls `json.loads(body)` directly), but the mismatch means any downstream analytics on items will produce wrong results.

#### G2 — Publisher hardcodes `localhost`

`groceror/engine/publisher.py` line 12:
```python
connection = pika.BlockingConnection(pika.ConnectionParameters("localhost"))
```

No credentials, no env var support. Breaks in any non-local environment.

#### G3 — Publisher opens a new TCP connection per message

A new `pika.BlockingConnection` is created and closed for every `publish_message()` call. Under load this causes connection churn and latency.

#### G4 — Publish failure is silently swallowed

`publisher.py` catches all exceptions and logs them. The caller in `order_api.py` never knows if the message was dropped. An order can be saved to PostgreSQL but never reach `groceror-orders`.

#### G5 — No dead-letter queue

There is no DLQ. A message that `groceror-orders` fails to process (e.g. MongoDB down) is ack'd and lost.

#### G6 — Analytics classes are stubs

`OrderAnalytics.most_selling_item()` and `least_selling_item()` have aggregation pipelines but:
- `most_selling_item` uses `{"$sum": "total_price"}` (missing `$` — will always sum 0)
- Both methods take `orders: List` but are called as if `orders` is a MongoDB collection object
- `OrderPerDayAnalytics` is a completely empty class
- No code calls these methods; no HTTP API exposes results

---

## 3. Proposed Architecture

```
groceror (FastAPI)
  POST /order/create-order
       │
       ├─► PostgreSQL  (source of truth, order persisted first)
       │
       └─► RabbitMQ
             exchange: "" (default direct)
             queue:    order_queue  (durable)
             DLQ:      order_queue.dlq (durable, bound to dlx exchange)
                  │
           groceror-orders (consumer)
                  │
                  ├─► MongoDB  orders.client_orders  (raw order store)
                  │
                  ├─► MongoDB  orders.analytics_daily   (pre-aggregated daily rollups)
                  │
                  └─► FastAPI  GET /analytics/*  (HTTP API for query results)
```

---

## 4. Message Contract

The canonical message schema published by `groceror` and consumed by `groceror-orders`.

### 4.1 Event: `order_created`

```json
{
  "event":       "order_created",
  "order_id":    "550e8400-e29b-41d4-a716-446655440000",
  "user_id":     "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
  "items":       ["inv-uuid-1", "inv-uuid-2"],
  "total_price": 12.50,
  "status":      "pending",
  "order_date":  "2026-04-12T10:30:00"
}
```

Field definitions:

| Field | Type | Source | Notes |
|---|---|---|---|
| `event` | `string` | publisher | Always `"order_created"` for this flow |
| `order_id` | `UUID string` | `Order.id` (PostgreSQL PK) | Globally unique, use for idempotency |
| `user_id` | `UUID string` | `User.id` | The User profile id, not PhoneVerification id |
| `items` | `string[]` | `Order.items` | Inventory UUIDs; resolved by groceror-orders if item names are needed |
| `total_price` | `float` | `Order.total_price` | |
| `status` | `string` | `Order.status` | `"pending"` at creation time |
| `order_date` | `ISO 8601 string` | `Order.order_date` | UTC |

### 4.2 Versioning

A `schema_version` field (`"1.0"`) is added to the envelope. `groceror-orders` must reject (NACK, route to DLQ) messages with an unknown version rather than silently misprocessing them.

---

## 5. Required Changes — `groceror`

### 5.1 Publisher: add env var configuration

Replace the hardcoded `"localhost"` connection with configurable parameters read from the app config or environment.

**Config additions** (`config.py` or `.config.yml`):
```yaml
groceror:
  rabbitmq:
    host: localhost
    port: 5672
    user: guest
    password: guest
    virtual_host: /
```

**`engine/publisher.py`** — replace current implementation:
- Read host/port/user/password from `RabbitMQConfig`
- Use a module-level singleton connection with reconnect-on-failure (replace per-call connect/close)
- Add `schema_version: "1.0"` to every published message
- Add `order_id` to the published payload (currently missing — `order_api.py` publishes `order.dict()` which uses the validator's fields, not the DB-assigned `id`)

### 5.2 Order API: publish the DB-assigned order id

`order_api.py` currently publishes `order.dict()` which reflects the request body. The DB-assigned `id` (the actual PostgreSQL PK) is not included. After `order_service.create_order()` returns the persisted entity, include `order_id` from the entity in the published message.

### 5.3 Publisher: do not swallow publish failures

`publish_message()` should raise an exception on failure (or return a boolean). `order_api.py` should log a warning when publish fails but still return HTTP 200 — the order is already saved. This makes failures observable rather than silent.

### 5.4 Dead-letter exchange setup

Declare a DLX (`dlx` exchange, `order_queue.dlq` queue) in the publisher's channel setup, and attach it to `order_queue` via `x-dead-letter-exchange`. Messages that `groceror-orders` NACKs (or that expire) will land in `order_queue.dlq` for inspection and replay.

---

## 6. Required Changes — `groceror-orders`

### 6.1 Fix consumer message processing

`order.py` currently calls `json.loads(body)` and saves raw dict to MongoDB without validation. Replace with:
1. Parse body → validate against updated `Order` schema (see §6.2)
2. On validation error → NACK with `requeue=False` (routes to DLQ)
3. On MongoDB write error → NACK with `requeue=True` (retry up to N times, then DLQ)
4. On success → ACK

### 6.2 Update `validator.py` to match the contract

```python
class Order(BaseModel):
    schema_version: str = "1.0"
    event:          str
    order_id:       UUID
    user_id:        UUID
    items:          List[str]   # inventory UUIDs (flat strings, not Item objects)
    total_price:    float
    status:         str
    order_date:     datetime
```

Remove the unused `Item` wrapper class.

### 6.3 MongoDB document structure

Each document saved to `orders.client_orders`:

```json
{
  "_id":          "<MongoDB ObjectId>",
  "order_id":     "550e8400-...",
  "user_id":      "6ba7b810-...",
  "items":        ["inv-uuid-1", "inv-uuid-2"],
  "total_price":  12.50,
  "status":       "pending",
  "order_date":   "2026-04-12T10:30:00",
  "received_at":  "2026-04-12T10:30:01",
  "schema_version": "1.0"
}
```

Add a unique index on `order_id` for idempotent re-processing.

### 6.4 Fix `OrderAnalytics`

**`analytics/order_analytics.py`** — fix the aggregation pipelines and make them callable with a collection:

```python
class OrderAnalytics:
    def __init__(self, db: DB):
        self.collection = db.get_collection("client_orders")

    def most_ordered_items(self, limit: int = 10) -> List[dict]:
        """Returns items ranked by order frequency."""
        pipeline = [
            {"$unwind": "$items"},
            {"$group": {"_id": "$items", "order_count": {"$sum": 1}}},
            {"$sort": {"order_count": -1}},
            {"$limit": limit},
        ]
        return list(self.collection.aggregate(pipeline))

    def revenue_by_item(self, limit: int = 10) -> List[dict]:
        """Returns items ranked by total revenue (approximated as total_price / item_count)."""
        pipeline = [
            {"$unwind": "$items"},
            {
                "$group": {
                    "_id": "$items",
                    "total_revenue": {
                        "$sum": {
                            "$divide": [
                                "$total_price",
                                {"$size": "$items"},
                            ]
                        }
                    },
                }
            },
            {"$sort": {"total_revenue": -1}},
            {"$limit": limit},
        ]
        return list(self.collection.aggregate(pipeline))

    def total_revenue(self) -> float:
        result = self.collection.aggregate([
            {"$group": {"_id": None, "total": {"$sum": "$total_price"}}}
        ])
        doc = next(result, None)
        return doc["total"] if doc else 0.0

    def order_count(self) -> int:
        return self.collection.count_documents({})
```

**`analytics/order_per_day_analytics.py`** — implement daily rollup:

```python
class OrderPerDayAnalytics:
    def __init__(self, db: DB):
        self.collection = db.get_collection("client_orders")

    def orders_per_day(self, days: int = 30) -> List[dict]:
        """Returns order count and revenue grouped by calendar day."""
        pipeline = [
            {
                "$group": {
                    "_id": {
                        "$dateToString": {
                            "format": "%Y-%m-%d",
                            "date": {"$toDate": "$order_date"},
                        }
                    },
                    "order_count": {"$sum": 1},
                    "total_revenue": {"$sum": "$total_price"},
                }
            },
            {"$sort": {"_id": -1}},
            {"$limit": days},
        ]
        return list(self.collection.aggregate(pipeline))
```

### 6.5 New: analytics HTTP API

Add a lightweight FastAPI app to `groceror-orders` so analytics results are queryable over HTTP:

```
GET /analytics/most-ordered-items?limit=10
GET /analytics/revenue-by-item?limit=10
GET /analytics/orders-per-day?days=30
GET /analytics/summary          # total orders + total revenue
```

This allows `groceror` (or any dashboard) to pull analytics without direct MongoDB access.

---

## 7. Infrastructure Requirements

### RabbitMQ

| Setting | Value |
|---|---|
| Queue | `order_queue`, durable=True |
| DLX exchange | `dlx`, type=direct |
| DLQ | `order_queue.dlq`, durable=True |
| Message TTL | None (persist until consumed) |
| Prefetch count | 1 (one message at a time in consumer) |
| Heartbeat | 600s |

### MongoDB

| Setting | Value |
|---|---|
| Database | `orders` |
| Collection (raw orders) | `client_orders` |
| Unique index | `order_id` (for idempotent reprocessing) |
| Collection (daily analytics) | `analytics_daily` (optional pre-aggregation cache) |

### Environment variables

**groceror:**
```
RABBITMQ_HOST=localhost
RABBITMQ_PORT=5672
RABBITMQ_USER=guest
RABBITMQ_PASS=guest
RABBITMQ_VHOST=/
```

**groceror-orders:**
```
RABBITMQ_HOST=localhost
RABBITMQ_USER=guest
RABBITMQ_PASS=guest
MONGO_URI=mongodb://...
ANALYTICS_API_PORT=8001
```

---

## 8. Error Handling & Reliability

| Failure scenario | groceror behaviour | groceror-orders behaviour |
|---|---|---|
| RabbitMQ unreachable at publish time | Log warning, return HTTP 200 (order saved to PG) | Reconnect loop with 5s backoff |
| Message fails validation in consumer | — | NACK, `requeue=False` → DLQ |
| MongoDB write fails | — | NACK, `requeue=True` (up to 3 retries), then DLQ |
| Duplicate `order_id` (redelivery) | — | Upsert by `order_id`, no double-count |
| Consumer crashes mid-processing | — | Message returns to queue (not ack'd) |

---

## 9. Observability

- `groceror/engine/publisher.py`: log `order_id` and queue name on every publish (INFO), log full exception on failure (ERROR)
- `groceror-orders/order.py`: log `order_id` on every successful save (INFO), log validation and DB errors (ERROR)
- RabbitMQ management UI (port 15672) to monitor queue depth and DLQ accumulation
- MongoDB: `received_at` timestamp on every document for lag measurement

---

## 10. Implementation Order

1. **Fix the message contract** — update `groceror/api/order_api.py` to include `order_id` (the PG PK) and `schema_version` in the published payload
2. **Configure the publisher** — add `RabbitMQConfig` to `groceror/config.py`, update `engine/publisher.py` to use env vars and a persistent connection
3. **Add the DLX** — declare `dlx` + `order_queue.dlq` in both publisher and consumer channel setup
4. **Fix the consumer validator** — update `groceror-orders/validator.py` to match the contract, add ACK/NACK logic in `order.py`
5. **Fix analytics** — rewrite `OrderAnalytics` and `OrderPerDayAnalytics` with correct pipelines and `DB` injection
6. **Add analytics API** — new `api.py` in `groceror-orders` with FastAPI routes
7. **Integration test** — end-to-end test: place order in groceror, assert document appears in MongoDB, assert analytics API returns updated counts

---

## 11. Out of Scope

- Authentication on the `groceror-orders` analytics API (first iteration: internal only)
- Historical backfill of existing PostgreSQL orders into MongoDB
- Real-time streaming / WebSocket push of analytics
- Item name resolution (items are stored as inventory UUIDs; mapping to names requires a join with groceror's PostgreSQL — deferred)
- Order status update events (`order_updated`, `order_cancelled`)
