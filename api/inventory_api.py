import logging
from datetime import datetime
from typing import List, Optional

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import select

from api.helpers.inventory_helper import InventoryHelper
from api.validators.inventory_validation import (
    AddInventoryPayload,
    AddInventoryResponse,
    DeleteInventoryResponse,
    SearchResponse,
    SearchResultItem,
    SetExpiryPayload,
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
            **add_inventory_payload.dict()
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
    store = helper._require_store()
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
    store = helper._require_store()
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
    user: PhoneVerification = Depends(auth_required),
):
    stmt = (
        select(Inventory)
        .where(Inventory.name.ilike(f"%{q}%"))
        .where(Inventory.quantity > 0)
    )
    if category:
        stmt = stmt.where(Inventory.category == category)
    items = db_session.exec(stmt).all()

    if not items:
        return SearchResponse(query=q, results=[])

    store_ids = list({item.store_id for item in items})
    active_stores = db_session.exec(
        select(Store).where(Store.id.in_(store_ids)).where(Store.is_active == True)
    ).all()
    store_map = {store.id: store.name for store in active_stores}

    return SearchResponse(
        query=q,
        results=[
            SearchResultItem(
                id=item.id,
                name=item.name,
                category=item.category,
                price=item.price,
                quantity=item.quantity,
                notes=item.notes,
                store_id=item.store_id,
                store_name=store_map[item.store_id],
            )
            for item in items
            if item.store_id in store_map
        ],
    )


@inventory_apis.get("/browse/{store_id}", response_model=StoreInventoryResponse)
async def browse_store_inventory(
    store_id: UUID,
    user: PhoneVerification = Depends(auth_required),
):
    items = db_session.exec(
        select(Inventory).where(Inventory.store_id == store_id)
    ).all()
    return StoreInventoryResponse(inventory=[StoreInventory(**item.to_dict()) for item in items])


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
