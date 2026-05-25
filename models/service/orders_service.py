import json
import logging
from uuid import UUID

from sqlmodel import select

from api.validators.order_validation import Order
from models.db import db_session
from models.entity.inventory_entity import Inventory
from models.entity.orders_entity import Order as OrderEntity

logger = logging.getLogger(__name__)


class UUIDEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, UUID):
            return str(obj)
        return super().default(obj)


class OrderService:
    def __init__(self):
        pass

    def create_order(self, order: Order, current_user) -> OrderEntity:
        """Persist the order and return the saved entity (with its DB-assigned id)."""
        try:
            store_id = None
            if order.items:
                first_item = db_session.exec(
                    select(Inventory).where(Inventory.id == order.items[0])
                ).first()
                if first_item:
                    store_id = first_item.store_id

            order_entity = OrderEntity(
                order_date=order.order_date,
                user_id=current_user.id,
                store_id=store_id,
                items=json.loads(json.dumps(order.items, cls=UUIDEncoder))
                if order.items
                else [],
                total_price=order.total_price,
                status=order.status,
            )
            db_session.add(order_entity)
            db_session.commit()
            db_session.refresh(order_entity)
            return order_entity
        except Exception as e:
            logger.error(f"Error creating order: {e}")
            db_session.rollback()
            raise e

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
