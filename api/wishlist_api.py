from datetime import datetime
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import select

from helpers.jwt import auth_required
from models.db import db_session
from models.entity.inventory_entity import Inventory
from models.entity.phone_verification import PhoneVerification
from models.entity.promotion_entity import Promotion
from models.entity.store_entity import Store
from models.entity.user_entity import User
from models.entity.wishlist_item_entity import WishlistItem

wishlist_apis = APIRouter(prefix="/wishlist", tags=["wishlist"])


def _get_user(entity: PhoneVerification = Depends(auth_required)) -> User:
    user = db_session.exec(select(User).where(User.entity_id == entity.id)).first()
    if not user:
        raise HTTPException(status_code=400, detail="User profile not set")
    return user


class AddWishlistPayload(BaseModel):
    inventory_id: UUID


class WishlistItemResponse(BaseModel):
    id: UUID
    inventory_id: UUID
    inventory_name: str
    store_id: UUID
    store_name: str
    price: float
    sale_price: Optional[float]
    stock: int
    is_in_stock: bool
    added_at: datetime


def _enrich(item: WishlistItem) -> Optional[WishlistItemResponse]:
    inv = db_session.exec(select(Inventory).where(Inventory.id == item.inventory_id)).first()
    if not inv:
        return None
    store = db_session.exec(select(Store).where(Store.id == inv.store_id)).first()

    # Check active promo
    from datetime import date
    today = date.today()
    promo = db_session.exec(
        select(Promotion).where(
            Promotion.inventory_id == inv.id,
            Promotion.start_date <= today,
            Promotion.end_date >= today,
        )
    ).first()

    return WishlistItemResponse(
        id=item.id,
        inventory_id=inv.id,
        inventory_name=inv.name,
        store_id=inv.store_id,
        store_name=store.name if store else "",
        price=inv.price,
        sale_price=promo.sale_price if promo else None,
        stock=inv.quantity,
        is_in_stock=inv.quantity > 0,
        added_at=item.created_at,
    )


@wishlist_apis.post("", response_model=WishlistItemResponse)
def add_to_wishlist(payload: AddWishlistPayload, user: User = Depends(_get_user)):
    inv = db_session.exec(select(Inventory).where(Inventory.id == payload.inventory_id)).first()
    if not inv:
        raise HTTPException(status_code=404, detail="Item not found")

    existing = db_session.exec(
        select(WishlistItem).where(
            WishlistItem.user_id == user.id,
            WishlistItem.inventory_id == payload.inventory_id,
        )
    ).first()
    if existing:
        return _enrich(existing)

    item = WishlistItem(user_id=user.id, inventory_id=payload.inventory_id)
    db_session.add(item)
    db_session.commit()
    db_session.refresh(item)
    return _enrich(item)


@wishlist_apis.get("", response_model=List[WishlistItemResponse])
def list_wishlist(user: User = Depends(_get_user)):
    items = db_session.exec(
        select(WishlistItem)
        .where(WishlistItem.user_id == user.id)
        .order_by(WishlistItem.created_at.desc())
    ).all()
    return [r for item in items if (r := _enrich(item)) is not None]


@wishlist_apis.get("/check/{inventory_id}", response_model=bool)
def check_wishlist(inventory_id: UUID, user: User = Depends(_get_user)):
    item = db_session.exec(
        select(WishlistItem).where(
            WishlistItem.user_id == user.id,
            WishlistItem.inventory_id == inventory_id,
        )
    ).first()
    return item is not None


@wishlist_apis.delete("/{inventory_id}", status_code=204)
def remove_from_wishlist(inventory_id: UUID, user: User = Depends(_get_user)):
    item = db_session.exec(
        select(WishlistItem).where(
            WishlistItem.user_id == user.id,
            WishlistItem.inventory_id == inventory_id,
        )
    ).first()
    if item:
        db_session.delete(item)
        db_session.commit()
