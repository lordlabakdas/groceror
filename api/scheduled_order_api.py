from datetime import date, datetime, timedelta
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import select

from api.validators.order_validation import CreateOrderRequest, OrderLineItem
from helpers.jwt import auth_required
from models.db import db_session
from models.entity.inventory_entity import Inventory
from models.entity.phone_verification import PhoneVerification
from models.entity.scheduled_order_entity import FREQUENCIES, ScheduledOrder
from models.entity.scheduled_order_item_entity import ScheduledOrderItem
from models.entity.store_entity import Store
from models.entity.user_entity import User
from models.service.orders_service import OrderService

scheduled_order_apis = APIRouter(prefix="/scheduled-orders", tags=["scheduled-orders"])
_svc = OrderService()

FREQ_DAYS = {"weekly": 7, "biweekly": 14, "monthly": 30}


def _get_user(entity: PhoneVerification = Depends(auth_required)) -> User:
    user = db_session.exec(select(User).where(User.entity_id == entity.id)).first()
    if not user:
        raise HTTPException(status_code=400, detail="User profile not set")
    return user


class ScheduledItemInput(BaseModel):
    inventory_id: UUID
    quantity: int = 1


class CreateScheduledOrderPayload(BaseModel):
    items: List[ScheduledItemInput]
    frequency: str  # "weekly" | "biweekly" | "monthly"
    start_date: Optional[date] = None  # defaults to today + frequency_days


class UpdateScheduledOrderPayload(BaseModel):
    frequency: Optional[str] = None
    is_active: Optional[bool] = None


class ScheduledItemResponse(BaseModel):
    inventory_id: UUID
    item_name: str
    quantity: int


class ScheduledOrderResponse(BaseModel):
    id: UUID
    store_id: UUID
    store_name: str
    frequency: str
    next_run_date: date
    is_active: bool
    last_run_at: Optional[datetime]
    created_at: datetime
    items: List[ScheduledItemResponse]


def _items_for(order_id: UUID) -> List[ScheduledItemResponse]:
    rows = db_session.exec(
        select(ScheduledOrderItem).where(ScheduledOrderItem.scheduled_order_id == order_id)
    ).all()
    return [ScheduledItemResponse(inventory_id=r.inventory_id, item_name=r.item_name, quantity=r.quantity) for r in rows]


def _to_response(so: ScheduledOrder) -> ScheduledOrderResponse:
    return ScheduledOrderResponse(
        id=so.id,
        store_id=so.store_id,
        store_name=so.store_name,
        frequency=so.frequency,
        next_run_date=so.next_run_date,
        is_active=so.is_active,
        last_run_at=so.last_run_at,
        created_at=so.created_at,
        items=_items_for(so.id),
    )


def _execute(so: ScheduledOrder, user: User) -> None:
    """Place an actual order from the scheduled template."""
    items = db_session.exec(
        select(ScheduledOrderItem).where(ScheduledOrderItem.scheduled_order_id == so.id)
    ).all()
    req = CreateOrderRequest(
        items=[OrderLineItem(inventory_id=i.inventory_id, quantity=i.quantity) for i in items]
    )
    try:
        _svc.create_order(req, user)
    except ValueError:
        pass  # item unavailable / store changed; skip silently

    days = FREQ_DAYS[so.frequency]
    so.next_run_date = date.today() + timedelta(days=days)
    so.last_run_at = datetime.utcnow()
    db_session.add(so)
    db_session.commit()


@scheduled_order_apis.post("", response_model=ScheduledOrderResponse)
def create_scheduled_order(payload: CreateScheduledOrderPayload, user: User = Depends(_get_user)):
    if payload.frequency not in FREQ_DAYS:
        raise HTTPException(status_code=400, detail="frequency must be weekly, biweekly, or monthly")
    if not payload.items:
        raise HTTPException(status_code=400, detail="At least one item required")

    # Validate all items belong to same store
    inv_ids = [i.inventory_id for i in payload.items]
    inventory_rows = db_session.exec(select(Inventory).where(Inventory.id.in_(inv_ids))).all()
    if len(inventory_rows) != len(inv_ids):
        raise HTTPException(status_code=400, detail="One or more items not found")

    store_ids = {inv.store_id for inv in inventory_rows}
    if len(store_ids) != 1:
        raise HTTPException(status_code=400, detail="All items must belong to the same store")

    store_id = store_ids.pop()
    store = db_session.exec(select(Store).where(Store.id == store_id)).first()
    inv_map = {inv.id: inv for inv in inventory_rows}

    days = FREQ_DAYS[payload.frequency]
    first_run = payload.start_date or (date.today() + timedelta(days=days))

    so = ScheduledOrder(
        user_id=user.id,
        store_id=store_id,
        store_name=store.name if store else "",
        frequency=payload.frequency,
        next_run_date=first_run,
    )
    db_session.add(so)
    db_session.flush()

    for item in payload.items:
        db_session.add(ScheduledOrderItem(
            scheduled_order_id=so.id,
            inventory_id=item.inventory_id,
            quantity=item.quantity,
            item_name=inv_map[item.inventory_id].name,
        ))

    db_session.commit()
    db_session.refresh(so)
    return _to_response(so)


@scheduled_order_apis.get("", response_model=List[ScheduledOrderResponse])
def list_scheduled_orders(user: User = Depends(_get_user)):
    orders = db_session.exec(
        select(ScheduledOrder)
        .where(ScheduledOrder.user_id == user.id)
        .order_by(ScheduledOrder.created_at.desc())
    ).all()

    # Auto-fire any overdue active orders
    today = date.today()
    for so in orders:
        if so.is_active and so.next_run_date <= today:
            _execute(so, user)

    db_session.expire_all()
    orders = db_session.exec(
        select(ScheduledOrder)
        .where(ScheduledOrder.user_id == user.id)
        .order_by(ScheduledOrder.created_at.desc())
    ).all()
    return [_to_response(so) for so in orders]


@scheduled_order_apis.put("/{order_id}", response_model=ScheduledOrderResponse)
def update_scheduled_order(
    order_id: UUID,
    payload: UpdateScheduledOrderPayload,
    user: User = Depends(_get_user),
):
    so = db_session.exec(
        select(ScheduledOrder).where(
            ScheduledOrder.id == order_id,
            ScheduledOrder.user_id == user.id,
        )
    ).first()
    if not so:
        raise HTTPException(status_code=404, detail="Scheduled order not found")

    if payload.frequency is not None:
        if payload.frequency not in FREQ_DAYS:
            raise HTTPException(status_code=400, detail="Invalid frequency")
        so.frequency = payload.frequency

    if payload.is_active is not None:
        so.is_active = payload.is_active

    db_session.add(so)
    db_session.commit()
    db_session.refresh(so)
    return _to_response(so)


@scheduled_order_apis.post("/{order_id}/run-now", response_model=ScheduledOrderResponse)
def run_now(order_id: UUID, user: User = Depends(_get_user)):
    so = db_session.exec(
        select(ScheduledOrder).where(
            ScheduledOrder.id == order_id,
            ScheduledOrder.user_id == user.id,
        )
    ).first()
    if not so:
        raise HTTPException(status_code=404, detail="Scheduled order not found")

    _execute(so, user)
    db_session.refresh(so)
    return _to_response(so)


@scheduled_order_apis.delete("/{order_id}", status_code=204)
def delete_scheduled_order(order_id: UUID, user: User = Depends(_get_user)):
    so = db_session.exec(
        select(ScheduledOrder).where(
            ScheduledOrder.id == order_id,
            ScheduledOrder.user_id == user.id,
        )
    ).first()
    if so:
        db_session.delete(so)
        db_session.commit()
