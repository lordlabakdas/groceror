from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlmodel import select

from helpers.jwt import auth_required
from models.db import db_session
from models.entity.phone_verification import PhoneVerification
from models.entity.user_entity import User
from models.service.cart_service import CartService

cart_apis = APIRouter(prefix="/cart", tags=["cart"])


class CartItemCreate(BaseModel):
    inventory_id: UUID
    quantity: int
    price: float
    notes: Optional[str] = None


class CartItemUpdate(BaseModel):
    quantity: Optional[int] = None
    price: Optional[float] = None
    notes: Optional[str] = None


def _get_user_profile(entity: PhoneVerification = Depends(auth_required)) -> User:
    """Resolve the User profile for the authenticated entity.

    Cart operations reference User.id (the profile table), so we need the
    User record that was created when the user set their profile.
    """
    user = db_session.exec(
        select(User).where(User.entity_id == entity.id)
    ).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User profile not set. Call /user/set-profile first.",
        )
    return user


@cart_apis.post("/{store_id}/items", status_code=status.HTTP_201_CREATED)
async def add_cart_item(
    store_id: UUID,
    item_data: CartItemCreate,
    current_user: User = Depends(_get_user_profile),
):
    return CartService(current_user).add_item(store_id, item_data)


@cart_apis.get("/{store_id}/items")
async def get_cart_items(
    store_id: UUID,
    current_user: User = Depends(_get_user_profile),
):
    return CartService(current_user).get_items(store_id)


@cart_apis.get("/all")
async def get_all_carts(current_user: User = Depends(_get_user_profile)):
    return CartService(current_user).get_store_carts()


@cart_apis.put("/{store_id}/items/{item_id}")
async def update_cart_item(
    store_id: UUID,
    item_id: UUID,
    item_data: CartItemUpdate,
    current_user: User = Depends(_get_user_profile),
):
    return CartService(current_user).update_item(store_id, item_id, item_data)


@cart_apis.delete("/{store_id}/items/{item_id}")
async def remove_cart_item(
    store_id: UUID,
    item_id: UUID,
    current_user: User = Depends(_get_user_profile),
):
    return CartService(current_user).remove_item(store_id, item_id)


@cart_apis.post("/{store_id}/clear")
async def clear_cart(
    store_id: UUID,
    current_user: User = Depends(_get_user_profile),
):
    return CartService(current_user).clear(store_id)


@cart_apis.get("/{store_id}/total")
async def get_cart_total(
    store_id: UUID,
    current_user: User = Depends(_get_user_profile),
):
    cart = CartService(current_user).get_active_cart(store_id)
    return {"total_price": cart.total_price, "total_quantity": cart.total_quantity}
