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
            missing_str = ", ".join(str(i) for i in missing)
            raise ValueError(f"Inventory items not found: {missing_str}")

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
