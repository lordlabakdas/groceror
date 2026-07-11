from datetime import datetime
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import select

from helpers.jwt import auth_required
from models.db import db_session
from models.entity.back_in_stock_alert_entity import BackInStockAlert
from models.entity.inventory_entity import Inventory
from models.entity.phone_verification import PhoneVerification
from models.entity.store_entity import Store
from models.entity.user_entity import User

back_in_stock_apis = APIRouter(prefix="/back-in-stock", tags=["back-in-stock"])


def _get_user(entity: PhoneVerification = Depends(auth_required)) -> User:
    user = db_session.exec(select(User).where(User.entity_id == entity.id)).first()
    if not user:
        raise HTTPException(status_code=400, detail="User profile not set")
    return user


class BackInStockResponse(BaseModel):
    id: UUID
    inventory_id: UUID
    inventory_name: str
    store_id: UUID
    store_name: str
    current_stock: int
    is_triggered: bool
    triggered_at: Optional[datetime]
    created_at: datetime


def _enrich(alert: BackInStockAlert) -> Optional[BackInStockResponse]:
    inv = db_session.exec(select(Inventory).where(Inventory.id == alert.inventory_id)).first()
    if not inv:
        return None
    store = db_session.exec(select(Store).where(Store.id == inv.store_id)).first()
    return BackInStockResponse(
        id=alert.id,
        inventory_id=inv.id,
        inventory_name=inv.name,
        store_id=inv.store_id,
        store_name=store.name if store else "",
        current_stock=inv.quantity,
        is_triggered=alert.is_triggered,
        triggered_at=alert.triggered_at,
        created_at=alert.created_at,
    )


def trigger_back_in_stock(inventory_id: UUID) -> None:
    """Called when an item's stock goes from 0 → positive. Triggers waiting alerts."""
    alerts = db_session.exec(
        select(BackInStockAlert).where(
            BackInStockAlert.inventory_id == inventory_id,
            BackInStockAlert.is_triggered == False,
        )
    ).all()
    from api.sse_bus import publish as sse_publish
    now = datetime.utcnow()
    for alert in alerts:
        alert.is_triggered = True
        alert.triggered_at = now
        db_session.add(alert)
    if alerts:
        db_session.commit()
        inv = db_session.exec(select(Inventory).where(Inventory.id == inventory_id)).first()
        inv_name = inv.name if inv else str(inventory_id)
        for alert in alerts:
            sse_publish(
                str(alert.user_id),
                "back_in_stock",
                {"inventory_id": str(inventory_id), "inventory_name": inv_name},
            )


@back_in_stock_apis.post("/{inventory_id}", response_model=BackInStockResponse)
def subscribe(inventory_id: UUID, user: User = Depends(_get_user)):
    inv = db_session.exec(select(Inventory).where(Inventory.id == inventory_id)).first()
    if not inv:
        raise HTTPException(status_code=404, detail="Item not found")
    if inv.quantity > 0:
        raise HTTPException(status_code=400, detail="Item is already in stock")

    existing = db_session.exec(
        select(BackInStockAlert).where(
            BackInStockAlert.user_id == user.id,
            BackInStockAlert.inventory_id == inventory_id,
        )
    ).first()
    if existing:
        return _enrich(existing)

    alert = BackInStockAlert(user_id=user.id, inventory_id=inventory_id)
    db_session.add(alert)
    db_session.commit()
    db_session.refresh(alert)
    return _enrich(alert)


@back_in_stock_apis.get("", response_model=List[BackInStockResponse])
def list_alerts(user: User = Depends(_get_user)):
    alerts = db_session.exec(
        select(BackInStockAlert)
        .where(BackInStockAlert.user_id == user.id)
        .order_by(BackInStockAlert.is_triggered.desc(), BackInStockAlert.created_at.desc())
    ).all()
    return [r for alert in alerts if (r := _enrich(alert)) is not None]


@back_in_stock_apis.delete("/{inventory_id}", status_code=204)
def unsubscribe(inventory_id: UUID, user: User = Depends(_get_user)):
    alert = db_session.exec(
        select(BackInStockAlert).where(
            BackInStockAlert.user_id == user.id,
            BackInStockAlert.inventory_id == inventory_id,
        )
    ).first()
    if alert:
        db_session.delete(alert)
        db_session.commit()
