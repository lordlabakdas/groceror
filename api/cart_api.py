from typing import List
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from helpers.jwt import auth_required
from models.entity.user_entity import User
from models.service.cart_service import CartService
from models.entity.cart_item_entity import CartItemEntity

cart_apis = APIRouter(prefix="/cart", tags=["cart"])


class CartItemCreate(BaseModel):
    inventory_id: UUID
    quantity: int
    price: float
    notes: str = None


class CartItemUpdate(BaseModel):
    quantity: int = None
    price: float = None
    notes: str = None


@cart_apis.post("/{store_id}/items", status_code=status.HTTP_201_CREATED)
async def add_cart_item(
    store_id: UUID,
    item_data: CartItemCreate,
    current_user: User = Depends(auth_required),
):
    cart_service = CartService(current_user)
    return cart_service.add_item(store_id, item_data)


@cart_apis.get("/{store_id}/items")
async def get_cart_items(store_id: UUID, current_user: User = Depends(auth_required)):
    cart_service = CartService(current_user)
    return cart_service.get_items(store_id)


@cart_apis.get("/all")
async def get_all_carts(current_user: User = Depends(auth_required)):
    cart_service = CartService(current_user)
    return cart_service.get_store_carts()


@cart_apis.put("/{store_id}/items/{item_id}")
async def update_cart_item(
    store_id: UUID,
    item_id: UUID,
    item_data: CartItemUpdate,
    current_user: User = Depends(auth_required),
):
    cart_service = CartService(current_user)
    return cart_service.update_item(store_id, item_id, item_data)


@cart_apis.delete("/{store_id}/items/{item_id}")
async def remove_cart_item(
    store_id: UUID, item_id: UUID, current_user: User = Depends(auth_required)
):
    cart_service = CartService(current_user)
    return cart_service.remove_item(store_id, item_id)


@cart_apis.post("/{store_id}/clear")
async def clear_cart(store_id: UUID, current_user: User = Depends(auth_required)):
    cart_service = CartService(current_user)
    return cart_service.clear(store_id)


@cart_apis.get("/{store_id}/total")
async def get_cart_total(store_id: UUID, current_user: User = Depends(auth_required)):
    cart_service = CartService(current_user)
    cart = cart_service.get_active_cart(store_id)
    return {"total_price": cart.total_price, "total_quantity": cart.total_quantity}
