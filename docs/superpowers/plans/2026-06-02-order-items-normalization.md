# Order Items Normalization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `Order.items ARRAY(String)` with a normalized `OrderItem` join table capturing `inventory_id`, `quantity`, and price-at-order-time per line.

**Architecture:** Add `OrderItem` as a first-class entity; rewrite `OrderService.create_order` to snapshot prices server-side and write line rows in one transaction; update read paths to JOIN on `OrderItem`; migrate existing array data on startup via `create_db_and_tables`.

**Tech Stack:** Python 3.11, FastAPI, SQLModel, SQLAlchemy, PostgreSQL (SQLite for unit tests), Pydantic v2, pytest

---

### Task 1: Create `OrderItem` entity

**Files:**
- Create: `models/entity/order_item_entity.py`
- Create: `tests/unit/test_order_item_entity.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_order_item_entity.py
from uuid import uuid4


def test_order_item_fields():
    from models.entity.order_item_entity import OrderItem
    order_id = uuid4()
    inv_id = uuid4()
    oi = OrderItem(order_id=order_id, inventory_id=inv_id, quantity=3, price=1.99)
    assert oi.order_id == order_id
    assert oi.inventory_id == inv_id
    assert oi.quantity == 3
    assert oi.price == 1.99


def test_order_item_defaults():
    from models.entity.order_item_entity import OrderItem
    oi = OrderItem(order_id=uuid4(), inventory_id=uuid4(), price=0.0)
    assert oi.quantity == 1
    assert oi.id is not None
    assert oi.created_at is not None
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
venv/bin/pytest tests/unit/test_order_item_entity.py -v
```
Expected: `ModuleNotFoundError` — `order_item_entity` doesn't exist yet.

- [ ] **Step 3: Create the entity**

```python
# models/entity/order_item_entity.py
from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel


class OrderItem(SQLModel, table=True):
    __tablename__ = "orderitem"

    id: Optional[UUID] = Field(default_factory=uuid4, primary_key=True)
    order_id: UUID = Field(foreign_key="order.id", index=True)
    inventory_id: UUID = Field(foreign_key="inventory.id", index=True)
    quantity: int = Field(default=1)
    price: float = Field(default=0.0)
    created_at: datetime = Field(default_factory=datetime.utcnow)
```

- [ ] **Step 4: Run test to confirm it passes**

```bash
venv/bin/pytest tests/unit/test_order_item_entity.py -v
```
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add models/entity/order_item_entity.py tests/unit/test_order_item_entity.py
git commit -m "feat: add OrderItem entity"
```

---

### Task 2: Remove `items` column from `Order`

**Files:**
- Modify: `models/entity/orders_entity.py`
- Create: `tests/unit/test_order_entity.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_order_entity.py
from uuid import uuid4


def test_order_has_no_items_column():
    from models.entity.orders_entity import Order
    assert not hasattr(Order, "items"), "Order.items ARRAY column should be removed"


def test_order_fields():
    from models.entity.orders_entity import Order
    o = Order(user_id=uuid4(), total_price=9.99, status="pending")
    assert o.status == "pending"
    assert o.total_price == 9.99
    assert o.order_id is not None
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
venv/bin/pytest tests/unit/test_order_entity.py -v
```
Expected: `test_order_has_no_items_column` FAILS — `Order` still has `items`.

- [ ] **Step 3: Replace `models/entity/orders_entity.py`**

```python
# models/entity/orders_entity.py
from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel


class Order(SQLModel, table=True):
    id: Optional[UUID] = Field(default_factory=uuid4, primary_key=True)
    # order_id kept for DB-schema compatibility (pre-existing NOT NULL column)
    order_id: UUID = Field(default_factory=uuid4)
    user_id: UUID = Field(foreign_key="user.id", index=True)
    store_id: Optional[UUID] = Field(default=None, foreign_key="store.id", index=True)
    total_price: float = Field(default=0.0)
    status: str = Field(default="pending", index=True)
    order_date: datetime = Field(default_factory=datetime.utcnow)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
venv/bin/pytest tests/unit/test_order_entity.py -v
```
Expected: 2 passed.

- [ ] **Step 5: Run full unit suite**

```bash
make test-unit
```
Expected: all pass (some tests reference `order.items` and will fail — those are fixed in Tasks 5 and 7).

- [ ] **Step 6: Commit**

```bash
git add models/entity/orders_entity.py tests/unit/test_order_entity.py
git commit -m "feat: remove Order.items ARRAY column"
```

---

### Task 3: Wire `OrderItem` into the DB layer and add startup migration

**Files:**
- Modify: `models/db.py`

- [ ] **Step 1: Add import and migration SQL to `models/db.py`**

Add this import after the existing entity imports (around line 15):

```python
from models.entity.order_item_entity import OrderItem  # noqa: F401
```

In `create_db_and_tables()`, after the existing `CREATE INDEX` block, add:

```python
        # OrderItem table + indexes (idempotent)
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS orderitem (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                order_id UUID NOT NULL REFERENCES "order"(id),
                inventory_id UUID NOT NULL REFERENCES inventory(id),
                quantity INTEGER NOT NULL DEFAULT 1,
                price FLOAT NOT NULL DEFAULT 0.0,
                created_at TIMESTAMP NOT NULL DEFAULT NOW()
            )
        """))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_orderitem_order_id ON orderitem (order_id)"
        ))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_orderitem_inventory_id ON orderitem (inventory_id)"
        ))

        # Migrate existing Order.items ARRAY → orderitem rows (runs only while items column exists)
        items_col = conn.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'order' AND column_name = 'items'"
        )).fetchone()
        if items_col:
            conn.execute(text("""
                INSERT INTO orderitem (id, order_id, inventory_id, quantity, price, created_at)
                SELECT
                    gen_random_uuid(),
                    o.id,
                    t.item_str::uuid,
                    1,
                    COALESCE(inv.price, 0.0),
                    NOW()
                FROM "order" o,
                LATERAL unnest(o.items) AS t(item_str)
                LEFT JOIN inventory inv ON inv.id = t.item_str::uuid
                WHERE o.items IS NOT NULL
                  AND array_length(o.items, 1) > 0
                  AND NOT EXISTS (
                      SELECT 1 FROM orderitem oi WHERE oi.order_id = o.id
                  )
            """))
            conn.execute(text('ALTER TABLE "order" DROP COLUMN IF EXISTS items'))
```

- [ ] **Step 2: Run full unit suite**

```bash
make test-unit
```
Expected: all pass (the migration SQL only runs against a live PostgreSQL, not the SQLite unit test DB).

- [ ] **Step 3: Commit**

```bash
git add models/db.py
git commit -m "feat: wire OrderItem into DB layer, add startup migration from ARRAY"
```

---

### Task 4: Update order validators

**Files:**
- Modify: `api/validators/order_validation.py`
- Create: `tests/unit/test_order_validators.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_order_validators.py
import pytest
from uuid import uuid4


def test_order_line_item_valid():
    from api.validators.order_validation import OrderLineItem
    item = OrderLineItem(inventory_id=uuid4(), quantity=2)
    assert item.quantity == 2


def test_order_line_item_default_quantity():
    from api.validators.order_validation import OrderLineItem
    item = OrderLineItem(inventory_id=uuid4())
    assert item.quantity == 1


def test_create_order_request_rejects_empty_items():
    from api.validators.order_validation import CreateOrderRequest
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        CreateOrderRequest(items=[])


def test_create_order_request_valid():
    from api.validators.order_validation import CreateOrderRequest, OrderLineItem
    req = CreateOrderRequest(items=[OrderLineItem(inventory_id=uuid4(), quantity=3)])
    assert len(req.items) == 1
    assert req.order_date is not None


def test_order_history_line_item():
    from api.validators.order_validation import OrderHistoryLineItem
    item = OrderHistoryLineItem(inventory_id=uuid4(), name="Apples", quantity=2, price=1.50)
    assert item.name == "Apples"
    assert item.price == 1.50


def test_store_order_line_item():
    from api.validators.order_validation import StoreOrderLineItem
    item = StoreOrderLineItem(inventory_id=uuid4(), name="Milk", quantity=1, price=2.00)
    assert item.name == "Milk"
```

- [ ] **Step 2: Run to confirm they fail**

```bash
venv/bin/pytest tests/unit/test_order_validators.py -v
```
Expected: `ImportError` on `CreateOrderRequest`, `OrderHistoryLineItem`, `StoreOrderLineItem`.

- [ ] **Step 3: Replace `api/validators/order_validation.py`**

```python
# api/validators/order_validation.py
from datetime import datetime
from typing import List
from uuid import UUID

from pydantic import BaseModel, Field

VALID_STATUSES = {"pending", "confirmed", "ready", "delivered", "cancelled"}


class OrderLineItem(BaseModel):
    inventory_id: UUID
    quantity: int = 1


class CreateOrderRequest(BaseModel):
    items: List[OrderLineItem] = Field(min_length=1)
    order_date: datetime = Field(default_factory=datetime.utcnow)


class OrderCreatedResponse(BaseModel):
    id: UUID
    status: str


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


class OrderHistoryResponse(BaseModel):
    orders: List[OrderHistoryItem]


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


class StoreOrdersResponse(BaseModel):
    orders: List[StoreOrderItem]


class UpdateOrderStatusPayload(BaseModel):
    status: str


class UpdateOrderStatusResponse(BaseModel):
    message: str
    status: str
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
venv/bin/pytest tests/unit/test_order_validators.py -v
```
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add api/validators/order_validation.py tests/unit/test_order_validators.py
git commit -m "feat: update order validators — CreateOrderRequest, line item types"
```

---

### Task 5: Rewrite `OrderService`

**Files:**
- Modify: `models/service/orders_service.py`
- Create: `tests/unit/test_order_service.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_order_service.py
import pytest
from unittest.mock import MagicMock, patch
from uuid import uuid4


def _make_inventory(inv_id, store_id, price=2.50):
    inv = MagicMock()
    inv.id = inv_id
    inv.store_id = store_id
    inv.price = price
    return inv


def test_create_order_snapshots_prices():
    from api.validators.order_validation import CreateOrderRequest, OrderLineItem
    from models.entity.order_item_entity import OrderItem
    from models.service.orders_service import OrderService

    store_id = uuid4()
    inv_id = uuid4()
    fake_inv = _make_inventory(inv_id, store_id, price=3.00)

    with patch("models.service.orders_service.db_session") as mock_db:
        mock_db.exec.return_value.all.return_value = [fake_inv]
        user = MagicMock()
        user.id = uuid4()

        req = CreateOrderRequest(items=[OrderLineItem(inventory_id=inv_id, quantity=2)])
        OrderService().create_order(req, user)

        # One Order add + one OrderItem add
        assert mock_db.add.call_count == 2
        mock_db.commit.assert_called_once()

        calls = mock_db.add.call_args_list
        order_items = [c[0][0] for c in calls if isinstance(c[0][0], OrderItem)]
        assert len(order_items) == 1
        assert order_items[0].price == 3.00
        assert order_items[0].quantity == 2


def test_create_order_computes_total_price():
    from api.validators.order_validation import CreateOrderRequest, OrderLineItem
    from models.entity.orders_entity import Order as OrderEntity
    from models.service.orders_service import OrderService

    store_id = uuid4()
    inv_id = uuid4()
    fake_inv = _make_inventory(inv_id, store_id, price=2.50)

    with patch("models.service.orders_service.db_session") as mock_db:
        mock_db.exec.return_value.all.return_value = [fake_inv]
        user = MagicMock()
        user.id = uuid4()

        req = CreateOrderRequest(items=[OrderLineItem(inventory_id=inv_id, quantity=4)])
        OrderService().create_order(req, user)

        calls = mock_db.add.call_args_list
        order_entities = [c[0][0] for c in calls if isinstance(c[0][0], OrderEntity)]
        assert len(order_entities) == 1
        assert order_entities[0].total_price == 10.00  # 4 * 2.50


def test_create_order_raises_if_inventory_missing():
    from api.validators.order_validation import CreateOrderRequest, OrderLineItem
    from models.service.orders_service import OrderService

    with patch("models.service.orders_service.db_session") as mock_db:
        mock_db.exec.return_value.all.return_value = []  # inventory not found
        user = MagicMock()
        user.id = uuid4()
        req = CreateOrderRequest(items=[OrderLineItem(inventory_id=uuid4(), quantity=1)])

        with pytest.raises(ValueError, match="not found"):
            OrderService().create_order(req, user)


def test_create_order_raises_if_mixed_stores():
    from api.validators.order_validation import CreateOrderRequest, OrderLineItem
    from models.service.orders_service import OrderService

    inv1_id, inv2_id = uuid4(), uuid4()
    inv1 = _make_inventory(inv1_id, uuid4(), price=1.0)
    inv2 = _make_inventory(inv2_id, uuid4(), price=2.0)  # different store_id

    with patch("models.service.orders_service.db_session") as mock_db:
        mock_db.exec.return_value.all.return_value = [inv1, inv2]
        user = MagicMock()
        user.id = uuid4()
        req = CreateOrderRequest(items=[
            OrderLineItem(inventory_id=inv1_id, quantity=1),
            OrderLineItem(inventory_id=inv2_id, quantity=1),
        ])

        with pytest.raises(ValueError, match="same store"):
            OrderService().create_order(req, user)
```

- [ ] **Step 2: Run to confirm they fail**

```bash
venv/bin/pytest tests/unit/test_order_service.py -v
```
Expected: all fail — `OrderService.create_order` still uses old signature.

- [ ] **Step 3: Replace `models/service/orders_service.py`**

```python
# models/service/orders_service.py
import logging
from uuid import UUID, uuid4

from sqlmodel import select

from api.validators.order_validation import CreateOrderRequest
from models.db import db_session
from models.entity.inventory_entity import Inventory
from models.entity.order_item_entity import OrderItem
from models.entity.orders_entity import Order as OrderEntity

logger = logging.getLogger(__name__)


class OrderService:
    def create_order(self, order: CreateOrderRequest, current_user) -> OrderEntity:
        inv_ids = [item.inventory_id for item in order.items]
        inventory_rows = db_session.exec(
            select(Inventory).where(Inventory.id.in_(inv_ids))
        ).all()
        inventory_map = {inv.id: inv for inv in inventory_rows}

        missing = [str(iid) for iid in inv_ids if iid not in inventory_map]
        if missing:
            raise ValueError(f"Inventory items not found: {', '.join(missing)}")

        store_ids = {inventory_map[iid].store_id for iid in inv_ids}
        if len(store_ids) != 1:
            raise ValueError("All order items must belong to the same store")
        store_id = store_ids.pop()

        total_price = round(
            sum(item.quantity * inventory_map[item.inventory_id].price for item in order.items), 2
        )

        try:
            order_id = uuid4()
            order_entity = OrderEntity(
                id=order_id,
                order_date=order.order_date,
                user_id=current_user.id,
                store_id=store_id,
                total_price=total_price,
                status="pending",
            )
            db_session.add(order_entity)

            for item in order.items:
                db_session.add(OrderItem(
                    order_id=order_id,
                    inventory_id=item.inventory_id,
                    quantity=item.quantity,
                    price=inventory_map[item.inventory_id].price,
                ))

            db_session.commit()
            db_session.refresh(order_entity)
            return order_entity
        except Exception as e:
            logger.error("Error creating order: %s", e)
            db_session.rollback()
            raise

    def get_order_by_id(self, order_id: UUID) -> OrderEntity:
        return db_session.exec(
            select(OrderEntity).where(OrderEntity.id == order_id)
        ).first()

    def get_orders_by_user(self, user_id: UUID) -> list[OrderEntity]:
        return db_session.exec(
            select(OrderEntity)
            .where(OrderEntity.user_id == user_id)
            .order_by(OrderEntity.order_date.desc())
        ).all()

    def get_orders_by_store(self, store_id: UUID) -> list[OrderEntity]:
        return db_session.exec(
            select(OrderEntity)
            .where(OrderEntity.store_id == store_id)
            .order_by(OrderEntity.order_date.desc())
        ).all()

    def update_order_status(self, order_id: UUID, store_id: UUID, new_status: str) -> OrderEntity:
        order = db_session.exec(
            select(OrderEntity)
            .where(OrderEntity.id == order_id)
            .where(OrderEntity.store_id == store_id)
        ).first()
        if not order:
            return None
        order.status = new_status
        db_session.commit()
        db_session.refresh(order)
        return order
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
venv/bin/pytest tests/unit/test_order_service.py -v
```
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add models/service/orders_service.py tests/unit/test_order_service.py
git commit -m "feat: rewrite OrderService — server-side price snapshot, OrderItem rows"
```

---

### Task 6: Update `order_api.py`

**Files:**
- Modify: `api/order_api.py`

- [ ] **Step 1: Replace `api/order_api.py`**

```python
# api/order_api.py
import logging
import uuid
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import select

from helpers.jwt import auth_required
from api.validators.order_validation import (
    CreateOrderRequest,
    OrderCreatedResponse,
    OrderHistoryItem,
    OrderHistoryLineItem,
    OrderHistoryResponse,
    StoreOrderItem,
    StoreOrderLineItem,
    StoreOrdersResponse,
    UpdateOrderStatusPayload,
    UpdateOrderStatusResponse,
    VALID_STATUSES,
)
from engine import publisher
from models.db import db_session
from models.entity.inventory_entity import Inventory
from models.entity.order_item_entity import OrderItem
from models.entity.phone_verification import PhoneVerification
from models.entity.store_entity import Store
from models.entity.user_entity import User
from models.service.orders_service import OrderService

logger = logging.getLogger(__name__)
order_apis = APIRouter(prefix="/order", tags=["order"])


def _get_store_profile(entity: PhoneVerification = Depends(auth_required)) -> Store:
    if entity.entity_type != "store":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Store access only")
    store = db_session.exec(select(Store).where(Store.entity_id == entity.id)).first()
    if not store:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Store profile not set. Call /user/set-profile first.",
        )
    return store


def _get_user_profile(entity: PhoneVerification = Depends(auth_required)) -> User:
    user = db_session.exec(select(User).where(User.entity_id == entity.id)).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User profile not set. Call /user/set-profile first.",
        )
    return user


def _serialize(obj):
    """Recursively convert UUIDs and datetimes to JSON-safe types."""
    if isinstance(obj, uuid.UUID):
        return str(obj)
    if isinstance(obj, list):
        return [_serialize(item) for item in obj]
    if isinstance(obj, dict):
        return {k: _serialize(v) for k, v in obj.items()}
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    return obj


@order_apis.get("/history", response_model=OrderHistoryResponse)
async def get_order_history(current_user: User = Depends(_get_user_profile)):
    orders = OrderService().get_orders_by_user(current_user.id)

    if not orders:
        return OrderHistoryResponse(orders=[])

    order_ids = [o.id for o in orders]
    rows = db_session.exec(
        select(OrderItem, Inventory)
        .join(Inventory, OrderItem.inventory_id == Inventory.id)
        .where(OrderItem.order_id.in_(order_ids))
    ).all()

    items_by_order: dict = defaultdict(list)
    for oi, inv in rows:
        items_by_order[oi.order_id].append(
            OrderHistoryLineItem(
                inventory_id=oi.inventory_id,
                name=inv.name,
                quantity=oi.quantity,
                price=oi.price,
            )
        )

    return OrderHistoryResponse(
        orders=[
            OrderHistoryItem(
                id=o.id,
                total_price=o.total_price,
                status=o.status,
                items=items_by_order[o.id],
                order_date=o.order_date,
            )
            for o in orders
        ]
    )


@order_apis.post("/create-order", response_model=OrderCreatedResponse)
async def create_order(
    order: CreateOrderRequest,
    current_user: User = Depends(_get_user_profile),
):
    logger.info("Creating order for user %s", current_user.id)
    try:
        order_entity = OrderService().create_order(order, current_user)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    order_dict = _serialize(order.dict())
    order_dict["order_id"] = str(order_entity.id)
    order_dict["user_id"] = str(current_user.id)
    order_dict["order_date"] = order.order_date.isoformat()

    try:
        publisher.publish_message(
            queue_name="order_queue",
            routing_key="order_queue",
            event="order_created",
            **order_dict,
        )
    except Exception:
        logger.warning("order_id=%s was saved but could not be published", order_entity.id)

    return OrderCreatedResponse(id=order_entity.id, status=order_entity.status)


@order_apis.get("/store-orders", response_model=StoreOrdersResponse)
async def get_store_orders(current_store: Store = Depends(_get_store_profile)):
    orders = OrderService().get_orders_by_store(current_store.id)

    if not orders:
        return StoreOrdersResponse(orders=[])

    order_ids = [o.id for o in orders]
    rows = db_session.exec(
        select(OrderItem, Inventory)
        .join(Inventory, OrderItem.inventory_id == Inventory.id)
        .where(OrderItem.order_id.in_(order_ids))
    ).all()

    items_by_order: dict = defaultdict(list)
    for oi, inv in rows:
        items_by_order[oi.order_id].append(
            StoreOrderLineItem(
                inventory_id=oi.inventory_id,
                name=inv.name,
                quantity=oi.quantity,
                price=oi.price,
            )
        )

    return StoreOrdersResponse(
        orders=[
            StoreOrderItem(
                id=o.id,
                total_price=o.total_price,
                status=o.status,
                items=items_by_order[o.id],
                order_date=o.order_date,
            )
            for o in orders
        ]
    )


@order_apis.put("/{order_id}/status", response_model=UpdateOrderStatusResponse)
async def update_order_status(
    order_id: uuid.UUID,
    payload: UpdateOrderStatusPayload,
    current_store: Store = Depends(_get_store_profile),
):
    if payload.status not in VALID_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid status. Must be one of: {', '.join(sorted(VALID_STATUSES))}",
        )
    updated = OrderService().update_order_status(order_id, current_store.id, payload.status)
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    try:
        publisher.publish_message(
            queue_name="order_queue",
            routing_key="order_queue",
            event="order_status_updated",
            order_id=str(order_id),
            store_id=str(current_store.id),
            status=payload.status,
        )
    except Exception:
        logger.warning("order_id=%s status updated but could not be published", order_id)
    return UpdateOrderStatusResponse(message="Status updated", status=updated.status)
```

- [ ] **Step 2: Run full unit suite**

```bash
make test-unit
```
Expected: all pass (dashboard tests will still fail on `_compute_top_sellers` — fixed in Task 7).

- [ ] **Step 3: Commit**

```bash
git add api/order_api.py
git commit -m "feat: update order routes — CreateOrderRequest, JOIN OrderItem for responses"
```

---

### Task 7: Update `_compute_top_sellers` in dashboard

**Files:**
- Modify: `api/dashboard_api.py`
- Modify: `tests/unit/test_dashboard.py`

- [ ] **Step 1: Update the `_compute_top_sellers` unit tests in `tests/unit/test_dashboard.py`**

Replace the three `_compute_top_sellers` tests (search for `test_compute_top_sellers_counts_correctly`, `test_compute_top_sellers_skips_invalid_uuid`, `test_compute_top_sellers_skips_missing_inventory`) with:

```python
def test_compute_top_sellers_counts_correctly():
    from api.dashboard_api import _compute_top_sellers
    from uuid import uuid4

    id1, id2 = uuid4(), uuid4()

    class FakeOrderItem:
        def __init__(self, inventory_id, quantity):
            self.inventory_id = inventory_id
            self.quantity = quantity

    class FakeItem:
        def __init__(self, uid, name, price):
            self.id = uid
            self.name = name
            self.price = price

    order_items = [
        FakeOrderItem(id1, 2),
        FakeOrderItem(id1, 1),
        FakeOrderItem(id2, 1),
    ]
    inventory_map = {
        id1: FakeItem(id1, "Apples", 3.00),
        id2: FakeItem(id2, "Milk", 2.50),
    }

    results = _compute_top_sellers(order_items, inventory_map)
    assert results[0].name == "Apples"
    assert results[0].units_sold == 3
    assert results[0].revenue == 9.00
    assert results[1].name == "Milk"
    assert results[1].units_sold == 1


def test_compute_top_sellers_skips_missing_inventory():
    from api.dashboard_api import _compute_top_sellers
    from uuid import uuid4

    class FakeOrderItem:
        def __init__(self, inventory_id, quantity):
            self.inventory_id = inventory_id
            self.quantity = quantity

    id1 = uuid4()
    results = _compute_top_sellers([FakeOrderItem(id1, 1)], {})
    assert results == []
```

(`test_compute_top_sellers_skips_invalid_uuid` is deleted — `inventory_id` is always a typed UUID at the DB level.)

- [ ] **Step 2: Run to confirm the tests fail**

```bash
venv/bin/pytest tests/unit/test_dashboard.py::test_compute_top_sellers_counts_correctly tests/unit/test_dashboard.py::test_compute_top_sellers_skips_missing_inventory -v
```
Expected: both fail — `_compute_top_sellers` still iterates over `order.items` strings.

- [ ] **Step 3: Update `_compute_top_sellers` in `api/dashboard_api.py`**

Add import at the top (after the existing imports):
```python
from models.entity.order_item_entity import OrderItem
```

Replace the `_compute_top_sellers` function:
```python
def _compute_top_sellers(
    order_items: list,
    inventory_map: dict,
    top_n: int = 5,
) -> list[TopSellerItem]:
    counter: Counter = Counter()
    for oi in order_items:
        counter[oi.inventory_id] += oi.quantity

    result = []
    for inv_id, units_sold in counter.most_common():
        if len(result) >= top_n:
            break
        item = inventory_map.get(inv_id)
        if item:
            result.append(TopSellerItem(
                id=item.id,
                name=item.name,
                units_sold=units_sold,
                revenue=round(units_sold * item.price, 2),
            ))
    return result
```

Replace the "Top sellers" block inside `get_dashboard` (the `week_start` / `recent_orders` block at the bottom):
```python
    # --- Top sellers (last 7 days) -------------------------------------------
    week_start = today_utc - timedelta(days=7)
    recent_order_items = db_session.exec(
        select(OrderItem)
        .join(OrderEntity, OrderItem.order_id == OrderEntity.id)
        .where(
            OrderEntity.store_id == store.id,
            OrderEntity.order_date >= week_start,
            OrderEntity.status != "cancelled",
        )
    ).all()
    top_sellers = _compute_top_sellers(recent_order_items, inventory_map)
```

- [ ] **Step 4: Run dashboard tests**

```bash
venv/bin/pytest tests/unit/test_dashboard.py -v
```
Expected: all pass.

- [ ] **Step 5: Run full unit suite**

```bash
make test-unit
```
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add api/dashboard_api.py tests/unit/test_dashboard.py
git commit -m "feat: update _compute_top_sellers to use OrderItem rows with quantity"
```

---

### Task 8: Fix integration tests and push

**Files:**
- Modify: `tests/integration/test_platform.py`

- [ ] **Step 1: Replace the `TestOrders` class in `tests/integration/test_platform.py`**

```python
class TestOrders:

    @patch("engine.publisher.publish_message")
    def test_create_order(self, mock_publish, user_token, user_profile, inventory_id):
        r = client.post(
            "/order/create-order",
            json={"items": [{"inventory_id": inventory_id, "quantity": 2}]},
            headers=_headers(user_token),
        )
        assert r.status_code == 200
        data = r.json()
        assert "id" in data
        assert data["status"] == "pending"
        mock_publish.assert_called_once()

    @patch("engine.publisher.publish_message")
    def test_create_order_empty_items_rejected(self, mock_publish, user_token, user_profile):
        r = client.post(
            "/order/create-order",
            json={"items": []},
            headers=_headers(user_token),
        )
        assert r.status_code == 422

    def test_create_order_requires_auth(self):
        r = client.post(
            "/order/create-order",
            json={"items": [{"inventory_id": "00000000-0000-0000-0000-000000000000", "quantity": 1}]},
        )
        assert r.status_code == 401

    def test_create_order_requires_profile(self, store_token):
        phone = f"+1555{_suffix}98"
        _otp_and_verify(phone)
        _register(phone, "user")
        token = _login(phone)
        with patch("engine.publisher.publish_message"):
            r = client.post(
                "/order/create-order",
                json={"items": [{"inventory_id": "00000000-0000-0000-0000-000000000000", "quantity": 1}]},
                headers=_headers(token),
            )
        assert r.status_code == 400
        assert "set-profile" in r.json()["detail"]
```

- [ ] **Step 2: Run full unit suite one final time**

```bash
make test-unit
```
Expected: all pass.

- [ ] **Step 3: Commit and push**

```bash
git add tests/integration/test_platform.py
git commit -m "test: update integration tests for normalized order items contract"
git push origin master
```
