from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID

from sqlmodel import func, select

from models.db import db_session
from models.entity.cart_entity import CartEntity
from models.entity.cart_item_entity import CartItemEntity
from models.entity.inventory_entity import Inventory
from models.entity.inventory_reservation_entity import InventoryReservation
from models.entity.user_entity import User

RESERVATION_MINUTES = 20


class InventoryReservationService:
    def __init__(self, user: User):
        self.user = user

    @staticmethod
    def expire_stale(cart_id: Optional[UUID] = None) -> None:
        now = datetime.utcnow()
        query = select(InventoryReservation).where(
            InventoryReservation.status == "active",
            InventoryReservation.expires_at <= now,
        )
        if cart_id:
            query = query.where(InventoryReservation.cart_id == cart_id)
        for reservation in db_session.exec(query).all():
            reservation.status = "expired"
            reservation.updated_at = now
            db_session.add(reservation)
        db_session.flush()

    @staticmethod
    def _reserved_elsewhere(inventory_id: UUID, cart_id: UUID) -> int:
        now = datetime.utcnow()
        total = db_session.exec(
            select(func.coalesce(func.sum(InventoryReservation.quantity), 0)).where(
                InventoryReservation.inventory_id == inventory_id,
                InventoryReservation.cart_id != cart_id,
                InventoryReservation.status == "active",
                InventoryReservation.expires_at > now,
            )
        ).one()
        return int(total or 0)

    def reserve(self, store_id: UUID) -> dict:
        cart = db_session.exec(
            select(CartEntity).where(
                CartEntity.user_id == self.user.id,
                CartEntity.store_id == store_id,
                CartEntity.is_active == True,
            )
        ).first()
        if not cart or not cart.items:
            raise ValueError("Cart is empty")

        self.expire_stale(cart.id)
        now = datetime.utcnow()
        expires_at = now + timedelta(minutes=RESERVATION_MINUTES)
        items = db_session.exec(
            select(CartItemEntity).where(CartItemEntity.cart_id == cart.id)
        ).all()
        for item in items:
            inventory = db_session.exec(
                select(Inventory).where(Inventory.id == item.inventory_id).with_for_update()
            ).first()
            if not inventory or inventory.store_id != store_id:
                raise ValueError("Inventory item is no longer available")
            available = inventory.quantity - self._reserved_elsewhere(inventory.id, cart.id)
            if item.quantity > available:
                raise ValueError(
                    f"Insufficient stock for {inventory.name}: requested {item.quantity}, available {max(available, 0)}"
                )
            reservation = db_session.exec(
                select(InventoryReservation).where(
                    InventoryReservation.cart_id == cart.id,
                    InventoryReservation.inventory_id == item.inventory_id,
                    InventoryReservation.status == "active",
                )
            ).first()
            if reservation:
                reservation.quantity = item.quantity
                reservation.expires_at = expires_at
                reservation.updated_at = now
            else:
                reservation = InventoryReservation(
                    user_id=self.user.id,
                    cart_id=cart.id,
                    inventory_id=item.inventory_id,
                    quantity=item.quantity,
                    expires_at=expires_at,
                )
            db_session.add(reservation)
        db_session.commit()
        return self.get(store_id)

    def get(self, store_id: UUID) -> dict:
        cart = db_session.exec(
            select(CartEntity).where(
                CartEntity.user_id == self.user.id,
                CartEntity.store_id == store_id,
                CartEntity.is_active == True,
            )
        ).first()
        if not cart:
            return {"status": "none", "expires_at": None, "remaining_seconds": 0}
        self.expire_stale(cart.id)
        active = db_session.exec(
            select(InventoryReservation).where(
                InventoryReservation.cart_id == cart.id,
                InventoryReservation.status == "active",
            ).order_by(InventoryReservation.expires_at)
        ).all()
        if not active:
            db_session.commit()
            return {"status": "expired", "expires_at": None, "remaining_seconds": 0}
        expires_at = min(row.expires_at for row in active)
        remaining = max(0, int((expires_at - datetime.utcnow()).total_seconds()))
        return {
            "status": "active",
            "expires_at": expires_at,
            "remaining_seconds": remaining,
            "items": [{"inventory_id": row.inventory_id, "quantity": row.quantity} for row in active],
        }

    def release(self, store_id: UUID) -> None:
        cart = db_session.exec(
            select(CartEntity).where(
                CartEntity.user_id == self.user.id,
                CartEntity.store_id == store_id,
                CartEntity.is_active == True,
            )
        ).first()
        if cart:
            for row in db_session.exec(select(InventoryReservation).where(
                InventoryReservation.cart_id == cart.id,
                InventoryReservation.status == "active",
            )).all():
                row.status = "released"
                row.updated_at = datetime.utcnow()
                db_session.add(row)
            db_session.commit()

    @staticmethod
    def consume_for_order(user_id: UUID, cart_id: Optional[UUID], inventory_ids: list[UUID]) -> None:
        if not cart_id:
            return
        rows = db_session.exec(select(InventoryReservation).where(
            InventoryReservation.user_id == user_id,
            InventoryReservation.cart_id == cart_id,
            InventoryReservation.inventory_id.in_(inventory_ids),
            InventoryReservation.status == "active",
        )).all()
        for row in rows:
            row.status = "consumed"
            row.updated_at = datetime.utcnow()
            db_session.add(row)
