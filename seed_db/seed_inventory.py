"""Seed script: inserts a test store + inventory items into the DB."""

import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlmodel import Session, select
from models.db import engine
from models.entity.phone_verification import PhoneVerification
from models.entity.store_entity import Store
from models.entity.inventory_entity import Inventory, InventoryCategory
from api.helpers.auth_helper import hash_password

STORE = {
    "name": "Test Grocer",
    "email": "testgrocer@example.com",
    "website": "https://testgrocer.example.com",
    "location": "Chicago, IL",
    "phone": "+13125550100",
}

INVENTORY_ITEMS = [
    {"name": "Whole Milk", "category": InventoryCategory.DAIRY, "quantity": 50, "price": 3.49},
    {"name": "Sourdough Bread", "category": InventoryCategory.BAKERY, "quantity": 20, "price": 5.99},
    {"name": "Chicken Breast", "category": InventoryCategory.MEAT, "quantity": 30, "price": 8.99},
    {"name": "Roma Tomatoes", "category": InventoryCategory.PRODUCE, "quantity": 100, "price": 1.29},
    {"name": "Basmati Rice 5lb", "category": InventoryCategory.GROCERY, "quantity": 40, "price": 6.49},
    {"name": "Cheddar Cheese", "category": InventoryCategory.DAIRY, "quantity": 25, "price": 4.79},
]


def _get_or_create_store(session: Session, hashed_password: str) -> Store:
    store = session.exec(select(Store).where(Store.email == STORE["email"])).first()
    if store:
        print(f"  ~ store already exists: {store.name} (id={store.id})")
        return store

    phone_verification = PhoneVerification(
        id=uuid.uuid4(),
        phone=STORE["phone"],
        entity_type="store",
        password=hashed_password,
        is_phone_verified=True,
    )
    session.add(phone_verification)
    session.flush()

    store = Store(
        name=STORE["name"],
        email=STORE["email"],
        website=STORE["website"],
        location=STORE["location"],
        entity_id=phone_verification.id,
        is_active=True,
    )
    session.add(store)
    session.flush()
    print(f"  + store created: {store.name} (id={store.id})")
    return store


def seed():
    plain_password = os.environ.get("SEED_PASSWORD")
    if not plain_password:
        raise RuntimeError("SEED_PASSWORD env var is not set. Add it to .env.")

    hashed = hash_password(plain_password)

    with Session(engine) as session:
        store = _get_or_create_store(session, hashed)

        for item in INVENTORY_ITEMS:
            inventory = Inventory(
                name=item["name"],
                category=item["category"],
                quantity=item["quantity"],
                price=item["price"],
                store_id=store.id,
            )
            session.add(inventory)
            print(f"  + inventory: {inventory.name} ({inventory.category}, qty={inventory.quantity})")

        session.commit()
        print(f"\nInserted {len(INVENTORY_ITEMS)} inventory items for store '{store.name}'.")


if __name__ == "__main__":
    seed()
