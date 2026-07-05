from datetime import datetime
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlmodel import select

from helpers.jwt import auth_required
from models.db import db_session
from models.entity.inventory_entity import Inventory
from models.entity.phone_verification import PhoneVerification
from models.entity.price_alert_entity import PriceAlert
from models.entity.user_entity import User

price_alert_apis = APIRouter(prefix="/price-alerts", tags=["price-alerts"])


def _get_user(entity: PhoneVerification = Depends(auth_required)) -> User:
    user = db_session.exec(select(User).where(User.entity_id == entity.id)).first()
    if not user:
        raise HTTPException(status_code=400, detail="User profile not set")
    return user


class CreatePriceAlertPayload(BaseModel):
    inventory_id: UUID
    target_price: float


class PriceAlertResponse(BaseModel):
    id: UUID
    inventory_id: UUID
    inventory_name: str
    current_price: float
    target_price: float
    is_triggered: bool
    is_active: bool
    created_at: datetime


def _check_and_trigger(inventory_id: UUID, new_price: float) -> None:
    """Called by inventory update paths to fire matching alerts."""
    alerts = db_session.exec(
        select(PriceAlert).where(
            PriceAlert.inventory_id == inventory_id,
            PriceAlert.is_active == True,
            PriceAlert.is_triggered == False,
            PriceAlert.target_price >= new_price,
        )
    ).all()
    for alert in alerts:
        alert.is_triggered = True
        alert.triggered_at = datetime.utcnow()
    if alerts:
        db_session.commit()


@price_alert_apis.post("", response_model=PriceAlertResponse)
def create_price_alert(
    payload: CreatePriceAlertPayload,
    current_user: User = Depends(_get_user),
):
    inventory = db_session.exec(
        select(Inventory).where(Inventory.id == payload.inventory_id)
    ).first()
    if not inventory:
        raise HTTPException(status_code=404, detail="Inventory item not found")

    existing = db_session.exec(
        select(PriceAlert).where(
            PriceAlert.user_id == current_user.id,
            PriceAlert.inventory_id == payload.inventory_id,
            PriceAlert.is_active == True,
        )
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="Active alert already exists for this item")

    already_met = inventory.price <= payload.target_price
    alert = PriceAlert(
        user_id=current_user.id,
        inventory_id=payload.inventory_id,
        target_price=payload.target_price,
        is_triggered=already_met,
        triggered_at=datetime.utcnow() if already_met else None,
    )
    db_session.add(alert)
    db_session.commit()
    db_session.refresh(alert)

    return PriceAlertResponse(
        id=alert.id,
        inventory_id=alert.inventory_id,
        inventory_name=inventory.name,
        current_price=inventory.price,
        target_price=alert.target_price,
        is_triggered=alert.is_triggered,
        is_active=alert.is_active,
        created_at=alert.created_at,
    )


@price_alert_apis.get("", response_model=List[PriceAlertResponse])
def list_price_alerts(current_user: User = Depends(_get_user)):
    alerts = db_session.exec(
        select(PriceAlert).where(
            PriceAlert.user_id == current_user.id,
            PriceAlert.is_active == True,
        )
    ).all()

    result = []
    for alert in alerts:
        inventory = db_session.exec(
            select(Inventory).where(Inventory.id == alert.inventory_id)
        ).first()
        if not inventory:
            continue
        result.append(
            PriceAlertResponse(
                id=alert.id,
                inventory_id=alert.inventory_id,
                inventory_name=inventory.name,
                current_price=inventory.price,
                target_price=alert.target_price,
                is_triggered=alert.is_triggered,
                is_active=alert.is_active,
                created_at=alert.created_at,
            )
        )
    return result


@price_alert_apis.delete("/{alert_id}", status_code=204)
def delete_price_alert(alert_id: UUID, current_user: User = Depends(_get_user)):
    alert = db_session.exec(
        select(PriceAlert).where(
            PriceAlert.id == alert_id,
            PriceAlert.user_id == current_user.id,
        )
    ).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    alert.is_active = False
    db_session.commit()
