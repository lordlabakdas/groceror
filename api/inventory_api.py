import logging
from datetime import date, datetime
from typing import List, Optional

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlmodel import select

from api.helpers.inventory_helper import InventoryHelper
from api.validators.inventory_validation import (
    AddInventoryPayload,
    AddInventoryResponse,
    DeleteInventoryResponse,
    SearchResponse,
    SearchResultItem,
    SetExpiryPayload,
    SetPromotionPayload,
    SetThresholdPayload,
    StoreInventory,
    StoreInventoryResponse,
    UpdateInventoryPayload,
    UpdateInventoryResponse,
)
from helpers.jwt import auth_required
from models.db import db_session
from models.entity.inventory_entity import Inventory, InventoryCategory
from models.entity.inventory_expiry_entity import InventoryExpiry
from models.entity.phone_verification import PhoneVerification
from models.entity.promotion_entity import Promotion
from models.entity.stock_threshold_entity import StockThreshold
from models.entity.store_entity import Store
from models.entity.user_entity import User

logger = logging.getLogger(__name__)
inventory_apis = APIRouter(prefix="/inventory", tags=["inventory"])


@inventory_apis.post("/add-inventory", response_model=AddInventoryResponse)
async def add_inventory(
    add_inventory_payload: AddInventoryPayload, user: PhoneVerification = Depends(auth_required)
):
    logger.info(f"Adding inventory for user: {add_inventory_payload}")
    try:
        inventory_helper_obj = InventoryHelper(user=user)
        new_inventory_id = inventory_helper_obj.add_inventory(
            **add_inventory_payload.model_dump()
        )
    except Exception as e:
        logger.exception(f"Error while adding inventory with exception details {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Issue with registering user",
        )
    else:
        return {"inventory_id": new_inventory_id}


@inventory_apis.get("/get-store-inventory", response_model=StoreInventoryResponse)
async def get_store_inventory(
    items: Optional[List[str]] = Query(default=None),
    user: User = Depends(auth_required),
):
    logger.info(f"Getting inventory for store: {user.phone}")
    try:
        inventory_helper_obj = InventoryHelper(user=user)
        inventory = inventory_helper_obj.get_store_inventory(items=items)
    except Exception as e:
        logger.exception(
            f"Error while retreiving store inventory with exception details {e}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Issue with retreiving store inventory",
        )
    else:
        return StoreInventoryResponse(inventory=inventory)


@inventory_apis.put("/{inventory_id}/threshold", response_model=UpdateInventoryResponse)
async def set_stock_threshold(
    inventory_id: UUID,
    payload: SetThresholdPayload,
    user: PhoneVerification = Depends(auth_required),
):
    helper = InventoryHelper(user=user)
    try:
        store = helper._require_store()
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    item = db_session.exec(
        select(Inventory).where(
            Inventory.id == inventory_id,
            Inventory.store_id == store.id,
        )
    ).first()
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Inventory item not found")
    existing = db_session.exec(
        select(StockThreshold).where(StockThreshold.inventory_id == inventory_id)
    ).first()
    if existing:
        existing.threshold = payload.threshold
        existing.updated_at = datetime.utcnow()
    else:
        db_session.add(StockThreshold(inventory_id=inventory_id, threshold=payload.threshold))
    db_session.commit()
    return {"status": "success"}


@inventory_apis.put("/{inventory_id}/expiry", response_model=UpdateInventoryResponse)
async def set_inventory_expiry(
    inventory_id: UUID,
    payload: SetExpiryPayload,
    user: PhoneVerification = Depends(auth_required),
):
    helper = InventoryHelper(user=user)
    try:
        store = helper._require_store()
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    item = db_session.exec(
        select(Inventory).where(
            Inventory.id == inventory_id,
            Inventory.store_id == store.id,
        )
    ).first()
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Inventory item not found")
    existing = db_session.exec(
        select(InventoryExpiry)
        .where(InventoryExpiry.inventory_id == inventory_id)
        .order_by(InventoryExpiry.updated_at.desc())
    ).first()
    if existing:
        existing.expiry_date = payload.expiry_date
        existing.updated_at = datetime.utcnow()
    else:
        db_session.add(InventoryExpiry(inventory_id=inventory_id, expiry_date=payload.expiry_date))
    db_session.commit()
    return {"status": "success"}


@inventory_apis.post("/{inventory_id}/promotion", response_model=UpdateInventoryResponse)
async def set_promotion(
    inventory_id: UUID,
    payload: SetPromotionPayload,
    user: PhoneVerification = Depends(auth_required),
):
    helper = InventoryHelper(user=user)
    try:
        store = helper._require_store()
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    item = db_session.exec(
        select(Inventory).where(Inventory.id == inventory_id, Inventory.store_id == store.id)
    ).first()
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Inventory item not found")
    if payload.end_date < payload.start_date:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="end_date must be on or after start_date")
    existing = db_session.exec(
        select(Promotion).where(Promotion.inventory_id == inventory_id)
    ).first()
    if existing:
        existing.sale_price = payload.sale_price
        existing.start_date = payload.start_date
        existing.end_date = payload.end_date
        existing.updated_at = datetime.utcnow()
    else:
        db_session.add(Promotion(
            inventory_id=inventory_id,
            sale_price=payload.sale_price,
            start_date=payload.start_date,
            end_date=payload.end_date,
        ))
    db_session.commit()
    return {"status": "success"}


@inventory_apis.delete("/{inventory_id}/promotion", response_model=UpdateInventoryResponse)
async def delete_promotion(
    inventory_id: UUID,
    user: PhoneVerification = Depends(auth_required),
):
    helper = InventoryHelper(user=user)
    try:
        store = helper._require_store()
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    item = db_session.exec(
        select(Inventory).where(Inventory.id == inventory_id, Inventory.store_id == store.id)
    ).first()
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Inventory item not found")
    promo = db_session.exec(
        select(Promotion).where(Promotion.inventory_id == inventory_id)
    ).first()
    if promo:
        db_session.delete(promo)
        db_session.commit()
    return {"status": "success"}


@inventory_apis.put("/{inventory_id}", response_model=UpdateInventoryResponse)
async def update_inventory(
    inventory_id: UUID,
    payload: UpdateInventoryPayload,
    user: PhoneVerification = Depends(auth_required),
):
    try:
        inventory_helper_obj = InventoryHelper(user=user)
        inventory_helper_obj.update_inventory_fields(
            inventory_id=inventory_id,
            quantity=payload.quantity,
            price=payload.price,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.exception(f"Error updating inventory: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Issue updating inventory",
        )
    return {"status": "success"}


@inventory_apis.get("/search", response_model=SearchResponse)
async def search_inventory(
    q: str = Query(min_length=2),
    category: Optional[InventoryCategory] = Query(default=None),
    min_price: Optional[float] = Query(default=None, ge=0),
    max_price: Optional[float] = Query(default=None, ge=0),
    in_stock: Optional[bool] = Query(default=None),
    store_id: Optional[UUID] = Query(default=None),
):
    stmt = select(Inventory).where(Inventory.name.ilike(f"%{q}%"))

    if in_stock is True or in_stock is None:
        stmt = stmt.where(Inventory.quantity > 0)
    if category:
        stmt = stmt.where(Inventory.category == category)
    if min_price is not None:
        stmt = stmt.where(Inventory.price >= min_price)
    if max_price is not None:
        stmt = stmt.where(Inventory.price <= max_price)
    if store_id is not None:
        stmt = stmt.where(Inventory.store_id == store_id)

    items = db_session.exec(stmt).all()

    if not items:
        return SearchResponse(query=q, results=[])

    store_ids = list({item.store_id for item in items})
    active_stores = db_session.exec(
        select(Store).where(Store.id.in_(store_ids)).where(Store.is_active == True)
    ).all()
    store_map = {store.id: store.name for store in active_stores}

    visible = [item for item in items if item.store_id in store_map]
    if visible:
        promos = db_session.exec(
            select(Promotion).where(
                Promotion.inventory_id.in_([item.id for item in visible]),
                Promotion.start_date <= date.today(),
                Promotion.end_date >= date.today(),
            )
        ).all()
        promo_map = {p.inventory_id: p.sale_price for p in promos}
    else:
        promo_map = {}

    from api.flash_sale_api import get_active_flash_sale
    search_results = []
    for item in visible:
        fs = get_active_flash_sale(item.id)
        search_results.append(SearchResultItem(
            id=item.id,
            name=item.name,
            category=item.category,
            price=item.price,
            quantity=item.quantity,
            notes=item.notes,
            store_id=item.store_id,
            store_name=store_map[item.store_id],
            sale_price=promo_map.get(item.id),
            flash_sale_price=fs.sale_price if fs else None,
            flash_sale_end_at=fs.end_at if fs else None,
        ))
    return SearchResponse(query=q, results=search_results)


@inventory_apis.get("/browse/{store_id}", response_model=StoreInventoryResponse)
async def browse_store_inventory(
    store_id: UUID,
    user: PhoneVerification = Depends(auth_required),
):
    items = db_session.exec(
        select(Inventory).where(Inventory.store_id == store_id)
    ).all()
    from api.flash_sale_api import get_active_flash_sale
    if items:
        promos = db_session.exec(
            select(Promotion).where(
                Promotion.inventory_id.in_([item.id for item in items]),
                Promotion.start_date <= date.today(),
                Promotion.end_date >= date.today(),
            )
        ).all()
        promo_map = {p.inventory_id: p.sale_price for p in promos}
    else:
        promo_map = {}
    result = []
    for item in items:
        fs = get_active_flash_sale(item.id)
        result.append(StoreInventory(
            **item.to_dict(),
            sale_price=promo_map.get(item.id),
            flash_sale_price=fs.sale_price if fs else None,
            flash_sale_end_at=fs.end_at if fs else None,
        ))
    return StoreInventoryResponse(inventory=result)


@inventory_apis.delete("/delete-inventory", response_model=DeleteInventoryResponse)
async def delete_inventory(
    items: Optional[List[str]] = Query(default=None),
    user: User = Depends(auth_required),
):
    logger.info(f"Deleting inventory for user: {user.phone}")
    try:
        inventory_helper_obj = InventoryHelper(user=user)
        inventory_helper_obj.delete_inventory(items=items)
    except Exception as e:
        logger.exception(f"Error while deleting inventory with exception details {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Issue with deleting inventory",
        )
    else:
        return {"status": "success"}


# ── Trending ────────────────────────────────────────────────────────────────

from datetime import timedelta


class TrendingItem(BaseModel):
    inventory_id: UUID
    inventory_name: str
    category: str
    price: float
    store_id: UUID
    store_name: str
    sale_price: Optional[float]
    flash_sale_price: Optional[float]
    flash_sale_end_at: Optional[datetime]
    order_count: int
    is_verified_store: bool


@inventory_apis.get("/trending", response_model=List[TrendingItem])
def get_trending(limit: int = Query(default=10, le=50)):
    from models.entity.order_item_entity import OrderItem
    from models.entity.orders_entity import Order as OrderEntity
    from api.flash_sale_api import get_active_flash_sale

    cutoff = datetime.utcnow() - timedelta(days=7)

    rows = db_session.exec(
        select(OrderItem.inventory_id)
        .join(OrderEntity, OrderItem.order_id == OrderEntity.id)
        .where(OrderEntity.created_at >= cutoff)
    ).all()

    if not rows:
        return []

    from collections import Counter
    counts = Counter(rows)
    top_ids = [inv_id for inv_id, _ in counts.most_common(limit * 2)]

    inventory_rows = db_session.exec(
        select(Inventory).where(Inventory.id.in_(top_ids), Inventory.quantity > 0)
    ).all()
    inv_map = {inv.id: inv for inv in inventory_rows}

    store_ids = {inv.store_id for inv in inventory_rows}
    stores = db_session.exec(
        select(Store).where(Store.id.in_(store_ids), Store.is_active == True)
    ).all()
    store_map = {s.id: s for s in stores}

    today = date.today()
    promos = db_session.exec(
        select(Promotion).where(
            Promotion.inventory_id.in_(top_ids),
            Promotion.start_date <= today,
            Promotion.end_date >= today,
        )
    ).all()
    promo_map = {p.inventory_id: p.sale_price for p in promos}

    result = []
    for inv_id, count in counts.most_common(limit * 2):
        inv = inv_map.get(inv_id)
        if not inv:
            continue
        store = store_map.get(inv.store_id)
        if not store:
            continue
        fs = get_active_flash_sale(inv.id)
        result.append(TrendingItem(
            inventory_id=inv.id,
            inventory_name=inv.name,
            category=inv.category,
            price=inv.price,
            store_id=inv.store_id,
            store_name=store.name,
            sale_price=promo_map.get(inv.id),
            flash_sale_price=fs.sale_price if fs else None,
            flash_sale_end_at=fs.end_at if fs else None,
            order_count=count,
            is_verified_store=store.is_verified,
        ))
        if len(result) >= limit:
            break

    return result
