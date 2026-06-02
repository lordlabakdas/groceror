# Order Items Normalization

**Date:** 2026-06-02
**Status:** Approved

## Problem

`Order.items` is a `ARRAY(String)` of raw inventory UUID strings. This means:
- No FK constraints to `Inventory`
- No quantity or price per line item
- Cannot query "all orders containing product X" efficiently
- `get_store_orders` requires a second round-trip to resolve UUIDs to names at read time

## Decision

Replace `Order.items` with a normalized `OrderItem` join table. Prices are snapshotted server-side from `Inventory` at order creation time. `total_price` on `Order` is retained as a paid-amount snapshot.

---

## Data Model

### New table: `orderitem`

| Column | Type | Constraints |
|---|---|---|
| `id` | UUID | PK, default uuid4 |
| `order_id` | UUID | FK → `order.id`, indexed |
| `inventory_id` | UUID | FK → `inventory.id`, indexed |
| `quantity` | int | default 1, ≥ 1 |
| `price` | float | snapshotted from `Inventory.price` at creation |
| `created_at` | datetime | default utcnow |

### Modified table: `order`

Remove column: `items ARRAY(String)`

All other columns unchanged (`id`, `order_id`, `user_id`, `store_id`, `total_price`, `status`, `order_date`, `created_at`, `updated_at`).

---

## Migration Strategy

Executed inside `create_db_and_tables()` on startup, idempotently:

1. `CREATE TABLE IF NOT EXISTS orderitem (...)`
2. For each existing order with a non-empty `items` array, insert one `orderitem` row per UUID (quantity=1, price looked up from `Inventory` or 0.0 if no longer exists)
3. `ALTER TABLE "order" DROP COLUMN IF EXISTS items`

Step 2 is wrapped in a check: skip rows already present in `orderitem` for a given `order_id` to make it safe to re-run.

---

## API Contract

### Request: `POST /order/create-order`

Before:
```json
{ "items": ["<uuid>", "<uuid>"], "total_price": 12.50, "status": "pending", "order_date": "..." }
```

After:
```json
{ "items": [{"inventory_id": "<uuid>", "quantity": 2}, {"inventory_id": "<uuid>", "quantity": 1}], "order_date": "..." }
```

`total_price` and `status` are removed from the request — computed and defaulted server-side respectively.

### Validators

```python
class OrderLineItem(BaseModel):
    inventory_id: UUID
    quantity: int = 1

class CreateOrderRequest(BaseModel):
    items: List[OrderLineItem]
    order_date: datetime = Field(default_factory=datetime.utcnow)
```

### Response: `GET /order/history`

Before: `items: List[str]` (raw UUID strings)

After:
```python
class OrderHistoryLineItem(BaseModel):
    inventory_id: UUID
    name: str
    quantity: int
    price: float

class OrderHistoryItem(BaseModel):
    id: UUID
    total_price: float
    status: str
    items: List[OrderHistoryLineItem]
    order_date: datetime
```

### Response: `GET /order/store-orders`

Before: `item_names: List[str]`

After:
```python
class StoreOrderLineItem(BaseModel):
    inventory_id: UUID
    name: str
    quantity: int
    price: float

class StoreOrderItem(BaseModel):
    id: UUID
    total_price: float
    status: str
    items: List[StoreOrderLineItem]
    order_date: datetime
```

---

## Service Logic

### `OrderService.create_order`

1. Validate `items` list is non-empty
2. Fetch all `Inventory` rows for the given `inventory_id`s — raise `ValueError` if any are missing
3. Assert all items belong to the same `store_id` — raise `ValueError` if not
4. Snapshot `price` from each `Inventory` row
5. Compute `total_price = sum(item.quantity * snapshotted_price)`
6. Insert `Order` row
7. Insert one `OrderItem` row per line item
8. Commit in a single transaction

### `OrderService.get_orders_by_user`

Returns `Order` rows joined to `OrderItem` joined to `Inventory` (for name). Returns structured line items; no ad-hoc resolution in the API layer.

### `OrderService.get_orders_by_store`

Same join pattern as above. Removes the batch-resolve logic currently inline in `order_api.get_store_orders`.

---

## Files Changed

| File | Change |
|---|---|
| `models/entity/order_item_entity.py` | New — `OrderItem` SQLModel table |
| `models/entity/orders_entity.py` | Remove `items` column |
| `models/db.py` | Import `OrderItem`; add CREATE TABLE, data migration, DROP COLUMN |
| `api/validators/order_validation.py` | Rename `Order` → `CreateOrderRequest`; add `OrderLineItem`, `StoreOrderLineItem`; update response models |
| `models/service/orders_service.py` | Rewrite `create_order`; update `get_orders_by_user`, `get_orders_by_store` |
| `api/order_api.py` | Update import `Order` → `CreateOrderRequest`; remove manual inventory resolution from `get_store_orders` |
| `tests/unit/test_dashboard.py` | Update order fixture to new schema |
| `tests/integration/test_platform.py` | Update order creation payloads |
