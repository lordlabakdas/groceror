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
from models.entity.stock_threshold_entity import StockThreshold
from models.entity.store_entity import Store

stock_alert_apis = APIRouter(prefix="/stock-alerts", tags=["stock-alerts"])


def _get_store(entity: PhoneVerification = Depends(auth_required)) -> Store:
    if entity.entity_type != "store":
        raise HTTPException(status_code=403, detail="Store account required")
    store = db_session.exec(select(Store).where(Store.entity_id == entity.id)).first()
    if not store:
        raise HTTPException(status_code=400, detail="Store profile not set")
    return store


class StockAlertResponse(BaseModel):
    id: UUID
    inventory_id: UUID
    inventory_name: str
    current_stock: int
    threshold: int
    is_triggered: bool
    triggered_at: Optional[datetime]
    acknowledged_at: Optional[datetime]


def _enrich(st: StockThreshold) -> Optional[StockAlertResponse]:
    inv = db_session.exec(select(Inventory).where(Inventory.id == st.inventory_id)).first()
    if not inv:
        return None
    return StockAlertResponse(
        id=st.id,
        inventory_id=inv.id,
        inventory_name=inv.name,
        current_stock=inv.quantity,
        threshold=st.threshold,
        is_triggered=st.is_triggered,
        triggered_at=st.triggered_at,
        acknowledged_at=st.acknowledged_at,
    )


@stock_alert_apis.get("", response_model=List[StockAlertResponse])
def list_stock_alerts(store: Store = Depends(_get_store)):
    inv_ids = db_session.exec(
        select(Inventory.id).where(Inventory.store_id == store.id)
    ).all()

    thresholds = db_session.exec(
        select(StockThreshold).where(StockThreshold.inventory_id.in_(inv_ids))
        .order_by(StockThreshold.is_triggered.desc(), StockThreshold.triggered_at.desc())
    ).all()

    return [r for st in thresholds if (r := _enrich(st)) is not None]


@stock_alert_apis.post("/{alert_id}/acknowledge", response_model=StockAlertResponse)
def acknowledge_alert(alert_id: UUID, store: Store = Depends(_get_store)):
    st = db_session.exec(select(StockThreshold).where(StockThreshold.id == alert_id)).first()
    if not st:
        raise HTTPException(status_code=404, detail="Alert not found")

    # Verify ownership
    inv = db_session.exec(
        select(Inventory).where(Inventory.id == st.inventory_id, Inventory.store_id == store.id)
    ).first()
    if not inv:
        raise HTTPException(status_code=403, detail="Not your inventory")

    st.acknowledged_at = datetime.utcnow()
    st.is_triggered = False
    db_session.add(st)
    db_session.commit()
    db_session.refresh(st)
    return _enrich(st)
