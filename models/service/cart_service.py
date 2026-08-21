from datetime import date, datetime
from typing import List
from uuid import UUID

from fastapi import HTTPException, status
from sqlmodel import select

from models.db import db_session
from models.entity.cart_entity import CartEntity
from models.entity.cart_item_entity import CartItemEntity
from models.entity.inventory_entity import Inventory
from models.entity.promotion_entity import Promotion
from models.entity.user_entity import User


def _resolve_effective_price(inventory: Inventory) -> float:
    """The price a shopper actually pays right now for this item.

    Never trust a client-supplied price for a cart line — CartItemCreate.price
    exists in the request schema, but honoring it let a shopper add an item
    at any price they chose to send, and separately caused the cart to show
    the regular price for flash-sale items regardless of what the item was
    actually discounted to. Same precedence as the display logic on the
    shopper browse page: flash sale first, then a running promotion, then
    the regular price."""
    from api.flash_sale_api import get_active_flash_sale

    fs = get_active_flash_sale(inventory.id)
    if fs:
        return fs.sale_price

    promo = db_session.exec(
        select(Promotion).where(
            Promotion.inventory_id == inventory.id,
            Promotion.start_date <= date.today(),
            Promotion.end_date >= date.today(),
        )
    ).first()
    if promo:
        return promo.sale_price

    return inventory.price


class CartService:
    def __init__(self, user: User):
        self.user = user
        self._active_cart = None

    def _get_or_create_cart(self, store_id: UUID) -> CartEntity:
        cart = db_session.exec(
            select(CartEntity).where(
                CartEntity.user_id == self.user.id,
                CartEntity.store_id == store_id,
                CartEntity.is_active == True,
            )
        ).first()
        if not cart:
            cart = CartEntity(user_id=self.user.id, store_id=store_id)
            db_session.add(cart)
            db_session.commit()
            db_session.refresh(cart)
        return cart

    def get_active_cart(self, store_id: UUID) -> CartEntity:
        if not self._active_cart or self._active_cart.store_id != store_id:
            self._active_cart = self._get_or_create_cart(store_id)
        return self._active_cart

    def add_item(self, store_id: UUID, item_data) -> CartItemEntity:
        try:
            inventory = db_session.exec(
                select(Inventory).where(
                    Inventory.id == item_data.inventory_id,
                    Inventory.store_id == store_id,
                )
            ).first()
            if not inventory:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Inventory item not found in this store",
                )
            if inventory.quantity < item_data.quantity:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Not enough inventory",
                )

            cart = self.get_active_cart(store_id)
            data = item_data.model_dump()
            data["price"] = _resolve_effective_price(inventory)
            cart_item = CartItemEntity(cart_id=cart.id, **data)
            db_session.add(cart_item)

            cart.total_quantity += cart_item.quantity
            cart.total_price += cart_item.price * cart_item.quantity
            cart.updated_at = datetime.utcnow()

            db_session.commit()
            db_session.refresh(cart_item)
            return cart_item
        except HTTPException:
            raise
        except Exception as e:
            db_session.rollback()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to add item to cart: {str(e)}",
            )

    def get_store_carts(self) -> List[CartEntity]:
        return db_session.exec(
            select(CartEntity).where(
                CartEntity.user_id == self.user.id,
                CartEntity.is_active == True,
            )
        ).all()

    def get_items(self, store_id: UUID) -> List[CartItemEntity]:
        cart = self.get_active_cart(store_id)
        return cart.items

    def update_item(self, store_id: UUID, item_id: UUID, item_data) -> CartItemEntity:
        cart = self.get_active_cart(store_id)
        try:
            cart_item = db_session.exec(
                select(CartItemEntity).where(
                    CartItemEntity.id == item_id,
                    CartItemEntity.cart_id == cart.id,
                )
            ).first()
            if not cart_item:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="Cart item not found"
                )

            old_quantity = cart_item.quantity
            old_price = cart_item.price
            new_quantity = item_data.quantity if item_data.quantity is not None else old_quantity

            # price is never client-settable (see _resolve_effective_price) —
            # re-derive it fresh instead, so a quantity update also picks up
            # a flash sale that started/ended since the item was added.
            inventory = db_session.exec(
                select(Inventory).where(Inventory.id == cart_item.inventory_id)
            ).first()
            new_price = _resolve_effective_price(inventory) if inventory else old_price

            for key, value in item_data.model_dump(exclude_unset=True, exclude={"price"}).items():
                setattr(cart_item, key, value)
            cart_item.price = new_price
            cart_item.updated_at = datetime.utcnow()

            cart.total_quantity += new_quantity - old_quantity
            cart.total_price += (new_quantity * new_price) - (old_quantity * old_price)
            cart.updated_at = datetime.utcnow()

            db_session.commit()
            db_session.refresh(cart_item)
            return cart_item
        except HTTPException:
            raise
        except Exception as e:
            db_session.rollback()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to update cart item: {str(e)}",
            )

    def remove_item(self, store_id: UUID, item_id: UUID) -> bool:
        cart = self.get_active_cart(store_id)
        try:
            cart_item = db_session.exec(
                select(CartItemEntity).where(
                    CartItemEntity.id == item_id,
                    CartItemEntity.cart_id == cart.id,
                )
            ).first()
            if not cart_item:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="Cart item not found"
                )

            cart.total_quantity -= cart_item.quantity
            cart.total_price -= cart_item.price * cart_item.quantity
            cart.updated_at = datetime.utcnow()

            db_session.delete(cart_item)
            db_session.commit()
            return True
        except HTTPException:
            raise
        except Exception as e:
            db_session.rollback()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to remove cart item: {str(e)}",
            )

    def clear(self, store_id: UUID) -> bool:
        cart = self.get_active_cart(store_id)
        try:
            items = db_session.exec(
                select(CartItemEntity).where(CartItemEntity.cart_id == cart.id)
            ).all()
            for item in items:
                db_session.delete(item)

            cart.total_quantity = 0
            cart.total_price = 0.0
            cart.updated_at = datetime.utcnow()

            db_session.commit()
            return True
        except Exception as e:
            db_session.rollback()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to clear cart: {str(e)}",
            )

    def get_total_price(self, store_id: UUID) -> float:
        return self.get_active_cart(store_id).total_price

    def get_total_quantity(self, store_id: UUID) -> int:
        return self.get_active_cart(store_id).total_quantity
