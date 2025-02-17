import logging
from enum import Enum
from typing import Dict, List

from helpers.db_helpers import DBHelper
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
                    category=InventoryCategory(category).name,
                    user_id=self.user.id,
                    notes=notes,
                )
            db_session.add(inventory_obj)
            db_session.commit()
            db_session.refresh(inventory_obj)
            return inventory_obj.id
        except Exception as e:
            logger.exception(f"Error while adding inventory with exception details {e}")
            raise e
        finally:
            db_session.close()

    def get_store_inventory(self, items: List[str] = None) -> List[Dict]:
        try:
            store_inventory = (
                db_session.query(Inventory)
                .join(User)
                .filter(User.id == self.user.id)
                .first()
            )
            if store_inventory:
                if items:
                    store_inventory = store_inventory.filter(
                        Inventory.name.in_(items)
                    ).all()
            else:
                logger.critical(f"No store inventory found for {self.user}")
        except Exception as e:
            logger.exception(f"Error while adding inventory with exception details {e}")
            raise e
        else:
            return DBHelper.convert_query_result_to_dict(query_result=store_inventory)
        finally:
            db_session.close()

    def get_inventory_by_category(self, category: Enum) -> List[Dict]:
        try:
            inventory = (
                db_session.query(Inventory)
                .join(User)
                .filter(User.id == self.user.id, Inventory.category == category)
                .all()
            )
        except Exception as e:
            logger.exception(
                f"Error while getting inventory by category with exception details {e}"
            )
            raise e
        else:
            return DBHelper.convert_query_result_to_dict(query_result=inventory)
        finally:
            db_session.close()

    def get_inventory_by_name(self, name: str) -> List[Dict]:
        try:
            inventory = (
                db_session.query(Inventory)
                .join(User)
                .filter(User.id == self.user.id, Inventory.name == name)
                .all()
            )
        except Exception as e:
            logger.exception(
                f"Error while getting inventory by name with exception details {e}"
            )
            raise e
        else:
            return DBHelper.convert_query_result_to_dict(query_result=inventory)
        finally:
            db_session.close()

    def update_inventory(self, inventory: dict) -> None:
        try:
            db_session.query(Inventory).filter(Inventory.id == inventory.id).update(
                inventory
            )
            db_session.commit()
        except Exception as e:
            logger.exception(
                f"Error while updating inventory with exception details {e}"
            )
            raise e
        finally:
            db_session.close()

    def delete_inventory(self, inventory: dict) -> None:
        try:
            db_session.query(Inventory).filter(Inventory.id == inventory.id).delete()
            db_session.commit()
        except Exception as e:
            logger.exception(
                f"Error while deleting inventory with exception details {e}"
            )
            raise e
