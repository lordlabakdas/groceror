from typing import List

from models.db import db_session
from models.entity.inventory_entity import Inventory


class InventoryService:
    def __init__(self, store_id: str):
        self.store_id = store_id

    def get_inventory(self) -> List[Inventory]:
        return (
            db_session.query(Inventory)
            .filter(Inventory.store_id == self.store_id)
            .all()
        )

    def add_inventory(
        self, inventory: Inventory, quantity: int, price: float, store_id: str
    ):
        inventory.quantity = quantity
        inventory.price = price
        inventory.store_id = store_id
        db_session.add(inventory)
        db_session.commit()

    def update_inventory(self, inventory: Inventory):
        db_session.commit()
