from datetime import datetime
from typing import List
from uuid import UUID

from fastapi import HTTPException, status
from sqlmodel import select

from models.db import db_session
from models.entity.cart_entity import CartEntity
from models.entity.cart_item_entity import CartItemEntity
from models.entity.inventory_entity import Inventory
from models.entity.user_entity import User


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
            cart_item = CartItemEntity(cart_id=cart.id, **item_data.model_dump())
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

            if item_data.quantity is not None:
                cart.total_quantity += item_data.quantity - cart_item.quantity
                cart.total_price += cart_item.price * (
                    item_data.quantity - cart_item.quantity
                )

            for key, value in item_data.model_dump(exclude_unset=True).items():
                setattr(cart_item, key, value)
            cart_item.updated_at = datetime.utcnow()
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
