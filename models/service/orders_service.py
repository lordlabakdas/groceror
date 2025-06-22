from typing import List
from uuid import UUID

from api.validators.order_validation import Order
from models.db import db_session
from models.entity.orders_entity import Order as OrderEntity


class OrderService:
    def __init__(self):
        pass

    def create_order(self, order: Order, current_user: str):
        order_entity = OrderEntity(
            order_id=order.order_id,
            order_date=order.order_date,
            user_id=current_user.id,
            items=order.items,
            total_price=order.total_price,
            status=order.status,
        )
        db_session.add(order_entity)
        db_session.commit()

    def get_order_by_id(self, order_id: UUID) -> Order:
        order = (
            db_session.query(OrderEntity)
            .filter(OrderEntity.order_id == order_id)
            .first()
        )
        return order
