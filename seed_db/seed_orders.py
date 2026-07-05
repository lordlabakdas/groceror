"""Seed script: inserts demo orders for the test store over the last 30 days.

Idempotent: order IDs are deterministic (uuid5 of a fixed namespace + index),
so re-running skips orders that already exist.
"""

import random
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlmodel import Session, select
from models.db import engine
from models.entity.inventory_entity import Inventory
from models.entity.order_item_entity import OrderItem
from models.entity.orders_entity import Order
from models.entity.store_entity import Store
from models.entity.user_entity import User

STORE_EMAIL = "testgrocer@example.com"
USER_EMAIL = "alice@example.com"
SEED_NAMESPACE = uuid.UUID("6f9619ff-8b86-4d01-b42d-00cf4fc964ff")
NUM_ORDERS = 28

# Weighted toward completed orders for past days; today's orders stay active.
PAST_STATUSES = ["delivered"] * 8 + ["cancelled"]
TODAY_STATUSES = ["pending", "confirmed", "ready"]


def seed():
    rng = random.Random(42)

    with Session(engine) as session:
        store = session.exec(select(Store).where(Store.email == STORE_EMAIL)).first()
        if not store:
            raise RuntimeError(f"Store {STORE_EMAIL} not found — run seed_inventory.py first.")

        user = session.exec(select(User).where(User.email == USER_EMAIL)).first()
        if not user:
            raise RuntimeError(f"User {USER_EMAIL} not found — run seed_users.py first.")

        inventory = session.exec(
            select(Inventory).where(Inventory.store_id == store.id)
        ).all()
        if not inventory:
            raise RuntimeError("Store has no inventory — run seed_inventory.py first.")

        now = datetime.utcnow()
        inserted = 0
        skipped = 0

        seed_ids = [uuid.uuid5(SEED_NAMESPACE, f"seed-order-{i}") for i in range(NUM_ORDERS)]
        existing_ids = set(
            session.exec(select(Order.id).where(Order.id.in_(seed_ids))).all()
        )

        for i in range(NUM_ORDERS):
            order_id = seed_ids[i]
            if order_id in existing_ids:
                skipped += 1
                continue

            # Spread orders over the last 30 days, denser in recent days.
            days_ago = min(int(rng.expovariate(1 / 8)), 29)
            order_date = (now - timedelta(days=days_ago)).replace(
                hour=rng.randint(8, 20), minute=rng.randint(0, 59)
            )

            line_items = rng.sample(inventory, k=rng.randint(1, 3))
            total = 0.0
            items = []
            for inv in line_items:
                qty = rng.randint(1, 4)
                total += inv.price * qty
                items.append((inv.id, qty, inv.price))

            status = rng.choice(TODAY_STATUSES if days_ago == 0 else PAST_STATUSES)

            session.add(Order(
                id=order_id,
                user_id=user.id,
                store_id=store.id,
                total_price=round(total, 2),
                status=status,
                order_date=order_date,
                created_at=order_date,
                updated_at=order_date,
            ))
            # Insert the order row before its items — without a relationship()
            # SQLAlchemy won't order these inserts for us.
            session.flush()
            for inv_id, qty, price in items:
                session.add(OrderItem(
                    id=uuid.uuid5(SEED_NAMESPACE, f"seed-order-{i}-item-{inv_id}"),
                    order_id=order_id,
                    inventory_id=inv_id,
                    quantity=qty,
                    price=price,
                    created_at=order_date,
                    updated_at=order_date,
                ))
            print(f"  + order {i:02d}: {order_date:%b %d %H:%M} — "
                  f"{len(items)} item(s), ${total:.2f}, {status}")
            inserted += 1

        session.commit()
        print(f"\nDone — inserted {inserted} orders, skipped {skipped}.")


if __name__ == "__main__":
    seed()
