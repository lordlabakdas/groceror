import logging
import uuid
from datetime import datetime
from enum import Enum
from typing import Dict, List

from sqlmodel import select

from models.db import db_session
from models.entity.inventory_entity import Inventory, InventoryCategory
from models.entity.phone_verification import PhoneVerification
from models.entity.store_entity import Store

logger = logging.getLogger()


class InventoryHelper:
    def __init__(self, user: PhoneVerification) -> None:
        self.entity = user  # PhoneVerification record from auth_required

        # Look up the Store owned by this entity
        self.store = db_session.exec(
            select(Store).where(Store.entity_id == self.entity.id)
        ).first()

    def _require_store(self) -> Store:
        if not self.store:
            raise ValueError("No store found for this account. Set your store profile first.")
        return self.store

    def add_inventory(
        self, name: str, quantity: int, category: Enum, price: float = 0.0, notes: str = None
    ) -> "uuid.UUID":
        store = self._require_store()

        inventory_obj = db_session.exec(
            select(Inventory).where(
                Inventory.store_id == store.id,
                Inventory.name == name,
            )
        ).first()

        if inventory_obj:
            inventory_obj.quantity += quantity
            if price > 0:
                inventory_obj.price = price
        else:
            inventory_obj = Inventory(
                name=name,
                quantity=quantity,
                category=InventoryCategory(category).name,
                store_id=store.id,
                price=price,
                notes=notes,
            )
            db_session.add(inventory_obj)

        db_session.commit()
        db_session.refresh(inventory_obj)
        return inventory_obj.id

    def get_store_inventory(self, items: List[str] = None) -> List[Dict]:
        store = self._require_store()
        query = select(Inventory).where(Inventory.store_id == store.id)
        if items:
            query = query.where(Inventory.name.in_(items))
        results = db_session.exec(query).all()
        return [inv.to_dict() for inv in results]

    def get_inventory_by_category(self, category: Enum) -> List[Dict]:
        store = self._require_store()
        results = db_session.exec(
            select(Inventory).where(
                Inventory.store_id == store.id,
                Inventory.category == category,
            )
        ).all()
        return [inv.to_dict() for inv in results]

    def get_inventory_by_name(self, name: str) -> List[Dict]:
        store = self._require_store()
        results = db_session.exec(
            select(Inventory).where(
                Inventory.store_id == store.id,
                Inventory.name == name,
            )
        ).all()
        return [inv.to_dict() for inv in results]

    def update_inventory_fields(
        self, inventory_id: uuid.UUID, quantity: int, price: float
    ) -> None:
        store = self._require_store()
        existing = db_session.exec(
            select(Inventory).where(
                Inventory.store_id == store.id,
                Inventory.id == inventory_id,
            )
        ).first()
        if not existing:
            raise ValueError("Inventory item not found")
        existing.quantity = quantity
        existing.price = price
        existing.updated_at = datetime.utcnow()
        db_session.commit()

    def update_inventory(self, inventory: Inventory) -> None:
        store = self._require_store()
        existing = db_session.exec(
            select(Inventory).where(
                Inventory.store_id == store.id,
                Inventory.id == inventory.id,
            )
        ).first()
        if not existing:
            raise ValueError(f"Inventory item not found")
        existing.quantity = inventory.quantity
        existing.price = inventory.price
        db_session.commit()

    def delete_inventory(self, items: List[str] = None) -> None:
        store = self._require_store()
        query = select(Inventory).where(Inventory.store_id == store.id)
        if items:
            query = query.where(Inventory.name.in_(items))
        results = db_session.exec(query).all()
        for inv in results:
            db_session.delete(inv)
        db_session.commit()
