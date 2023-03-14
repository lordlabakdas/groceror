import logging
from enum import Enum

from models.db import db_session
from models.entity.inventory_entity import Inventory, InventoryCategory
from models.entity.user_entity import User

logger = logging.getLogger()


class InventoryHelper(object):
    def __init__(self, user: User) -> None:
        self.user = user

    def add_inventory(
        self, name: str, quantity: int, category: Enum, notes: str = None
    ) -> dict:
        try:
            inventory_obj = (
                db_session.query(Inventory)
                .join(User)
                .filter(User.id == self.user.id, Inventory.name == name)
                .first()
            )
            if inventory_obj:
                inventory_obj.quantity += quantity
            else:
                inventory_obj = Inventory(
                    name=name,
                    quantity=quantity,
                    category=InventoryCategory(category),
                    user_id=self.user.id,
                    notes=notes,
                )
            db_session.add(inventory_obj)
            db_session.commit()
            db_session.refresh()
        except Exception as e:
            logger.exception(f"Error while adding inventory with exception details {e}")
            raise e
