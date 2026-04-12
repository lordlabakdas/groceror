import json
import logging
from uuid import UUID

from sqlmodel import select

from api.validators.order_validation import Order
from models.db import db_session
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

    def create_order(self, order: Order, current_user):
        try:
            order_entity = OrderEntity(
                order_date=order.order_date,
                user_id=current_user.id,
                items=json.loads(json.dumps(order.items, cls=UUIDEncoder))
                if order.items
                else [],
                total_price=order.total_price,
                status=order.status,
            )
            db_session.add(order_entity)
            db_session.commit()
        except Exception as e:
            logger.error(f"Error creating order: {e}")
            db_session.rollback()
            raise e

    def get_order_by_id(self, order_id: UUID) -> OrderEntity:
        return db_session.exec(
            select(OrderEntity).where(OrderEntity.id == order_id)
        ).first()
