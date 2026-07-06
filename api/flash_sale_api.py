from datetime import datetime
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field as PField
from sqlmodel import select

from helpers.jwt import auth_required
from models.db import db_session
from models.entity.flash_sale_entity import FlashSale
from models.entity.inventory_entity import Inventory
from models.entity.phone_verification import PhoneVerification
from models.entity.store_entity import Store

flash_sale_apis = APIRouter(prefix="/flash-sales", tags=["flash-sales"])


def _get_store(entity: PhoneVerification = Depends(auth_required)) -> Store:
    if entity.entity_type != "store":
        raise HTTPException(status_code=403, detail="Store account required")
    store = db_session.exec(select(Store).where(Store.entity_id == entity.id)).first()
    if not store:
        raise HTTPException(status_code=400, detail="Store profile not set")
    return store


class CreateFlashSalePayload(BaseModel):
    inventory_id: UUID
    sale_price: float = PField(..., gt=0)
    start_at: datetime
    end_at: datetime


class FlashSaleResponse(BaseModel):
    id: UUID
    inventory_id: UUID
    inventory_name: str
    store_id: UUID
    sale_price: float
    original_price: float
    start_at: datetime
    end_at: datetime
    is_active: bool
    is_live: bool
    seconds_remaining: Optional[int]
    created_at: datetime


def _enrich(fs: FlashSale) -> Optional[FlashSaleResponse]:
    inv = db_session.exec(select(Inventory).where(Inventory.id == fs.inventory_id)).first()
    if not inv:
        return None
    now = datetime.utcnow()
    is_live = fs.is_active and fs.start_at <= now <= fs.end_at
    secs = max(0, int((fs.end_at - now).total_seconds())) if is_live else None
    return FlashSaleResponse(
        id=fs.id,
        inventory_id=inv.id,
        inventory_name=inv.name,
        store_id=fs.store_id,
        sale_price=fs.sale_price,
        original_price=inv.price,
        start_at=fs.start_at,
        end_at=fs.end_at,
        is_active=fs.is_active,
        is_live=is_live,
        seconds_remaining=secs,
        created_at=fs.created_at,
    )


def get_active_flash_sale(inventory_id: UUID) -> Optional[FlashSale]:
    """Returns the active flash sale for an inventory item, if any."""
    now = datetime.utcnow()
    return db_session.exec(
        select(FlashSale).where(
            FlashSale.inventory_id == inventory_id,
            FlashSale.is_active == True,
            FlashSale.start_at <= now,
            FlashSale.end_at >= now,
        )
    ).first()


@flash_sale_apis.post("", response_model=FlashSaleResponse)
def create_flash_sale(payload: CreateFlashSalePayload, store: Store = Depends(_get_store)):
    if payload.end_at <= payload.start_at:
        raise HTTPException(status_code=400, detail="end_at must be after start_at")
    if payload.end_at <= datetime.utcnow():
        raise HTTPException(status_code=400, detail="end_at must be in the future")

    inv = db_session.exec(
        select(Inventory).where(Inventory.id == payload.inventory_id, Inventory.store_id == store.id)
    ).first()
    if not inv:
        raise HTTPException(status_code=404, detail="Inventory item not found")
    if payload.sale_price >= inv.price:
        raise HTTPException(status_code=400, detail="Flash sale price must be less than regular price")

    fs = FlashSale(
        inventory_id=payload.inventory_id,
        store_id=store.id,
        sale_price=payload.sale_price,
        start_at=payload.start_at,
        end_at=payload.end_at,
    )
    db_session.add(fs)
    db_session.commit()
    db_session.refresh(fs)
    return _enrich(fs)


@flash_sale_apis.get("/store", response_model=List[FlashSaleResponse])
def list_store_flash_sales(store: Store = Depends(_get_store)):
    sales = db_session.exec(
        select(FlashSale)
        .where(FlashSale.store_id == store.id)
        .order_by(FlashSale.created_at.desc())
    ).all()
    return [r for fs in sales if (r := _enrich(fs)) is not None]


@flash_sale_apis.get("/active", response_model=List[FlashSaleResponse])
def list_active_flash_sales():
    now = datetime.utcnow()
    sales = db_session.exec(
        select(FlashSale).where(
            FlashSale.is_active == True,
            FlashSale.start_at <= now,
            FlashSale.end_at >= now,
        ).order_by(FlashSale.end_at)
    ).all()
    return [r for fs in sales if (r := _enrich(fs)) is not None]


@flash_sale_apis.delete("/{sale_id}", status_code=204)
def cancel_flash_sale(sale_id: UUID, store: Store = Depends(_get_store)):
    fs = db_session.exec(
        select(FlashSale).where(FlashSale.id == sale_id, FlashSale.store_id == store.id)
    ).first()
    if not fs:
        raise HTTPException(status_code=404, detail="Flash sale not found")
    fs.is_active = False
    db_session.add(fs)
    db_session.commit()
