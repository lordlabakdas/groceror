from datetime import datetime
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlmodel import select

from helpers.jwt import auth_required
from models.db import db_session
from models.entity.dispute_entity import Dispute, DISPUTE_RESOLUTIONS
from models.entity.dispute_message_entity import DisputeMessage
from models.entity.orders_entity import Order
from models.entity.phone_verification import PhoneVerification
from models.entity.store_entity import Store
from models.entity.user_entity import User

dispute_apis = APIRouter(prefix="/disputes", tags=["disputes"])

DISPUTE_REASONS = {"wrong_item", "missing_item", "quality", "damaged", "not_delivered", "other"}


def _get_user_optional(entity: PhoneVerification = Depends(auth_required)) -> Optional[User]:
    if entity.entity_type != "user":
        return None
    return db_session.exec(select(User).where(User.entity_id == entity.id)).first()


def _get_store_optional(entity: PhoneVerification = Depends(auth_required)) -> Optional[Store]:
    if entity.entity_type != "store":
        return None
    return db_session.exec(select(Store).where(Store.entity_id == entity.id)).first()


class OpenDisputePayload(BaseModel):
    order_id: UUID
    reason: str
    description: str


class AddMessagePayload(BaseModel):
    message: str


class ResolveDisputePayload(BaseModel):
    resolution: str


class DisputeMessageOut(BaseModel):
    id: UUID
    sender_type: str
    message: str
    created_at: datetime


class DisputeOut(BaseModel):
    id: UUID
    order_id: UUID
    store_id: UUID
    reason: str
    description: str
    status: str
    resolution: Optional[str]
    created_at: datetime
    updated_at: datetime
    messages: List[DisputeMessageOut] = []


@dispute_apis.post("", response_model=DisputeOut)
def open_dispute(
    payload: OpenDisputePayload,
    entity: PhoneVerification = Depends(auth_required),
):
    if entity.entity_type != "user":
        raise HTTPException(status_code=403, detail="Shopper access only")

    user = db_session.exec(select(User).where(User.entity_id == entity.id)).first()
    if not user:
        raise HTTPException(status_code=400, detail="User profile not set")

    if payload.reason not in DISPUTE_REASONS:
        raise HTTPException(status_code=400, detail=f"Invalid reason. Valid: {sorted(DISPUTE_REASONS)}")

    order = db_session.exec(
        select(Order).where(Order.id == payload.order_id, Order.user_id == user.id)
    ).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    existing = db_session.exec(
        select(Dispute).where(
            Dispute.order_id == payload.order_id,
            Dispute.status.notin_(["resolved", "closed"]),
        )
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="An open dispute already exists for this order")

    dispute = Dispute(
        order_id=order.id,
        user_id=user.id,
        store_id=order.store_id,
        reason=payload.reason,
        description=payload.description,
    )
    db_session.add(dispute)
    db_session.commit()
    db_session.refresh(dispute)
    return _dispute_out(dispute)


@dispute_apis.get("", response_model=List[DisputeOut])
def list_disputes(entity: PhoneVerification = Depends(auth_required)):
    if entity.entity_type == "user":
        user = db_session.exec(select(User).where(User.entity_id == entity.id)).first()
        if not user:
            raise HTTPException(status_code=400, detail="User profile not set")
        disputes = db_session.exec(
            select(Dispute)
            .where(Dispute.user_id == user.id)
            .order_by(Dispute.created_at.desc())
        ).all()
    else:
        store = db_session.exec(select(Store).where(Store.entity_id == entity.id)).first()
        if not store:
            raise HTTPException(status_code=400, detail="Store profile not set")
        disputes = db_session.exec(
            select(Dispute)
            .where(Dispute.store_id == store.id)
            .order_by(Dispute.created_at.desc())
        ).all()

    return [_dispute_out(d) for d in disputes]


@dispute_apis.get("/{dispute_id}", response_model=DisputeOut)
def get_dispute(dispute_id: UUID, entity: PhoneVerification = Depends(auth_required)):
    dispute = _get_authorized_dispute(dispute_id, entity)
    return _dispute_out(dispute)


@dispute_apis.post("/{dispute_id}/messages", response_model=DisputeOut)
def add_message(
    dispute_id: UUID,
    payload: AddMessagePayload,
    entity: PhoneVerification = Depends(auth_required),
):
    dispute = _get_authorized_dispute(dispute_id, entity)
    if dispute.status in ("resolved", "closed"):
        raise HTTPException(status_code=400, detail="Cannot message on a resolved or closed dispute")

    sender_type = "shopper" if entity.entity_type == "user" else "store"

    if sender_type == "store" and dispute.status == "open":
        dispute.status = "store_responded"
        dispute.updated_at = datetime.utcnow()

    msg = DisputeMessage(
        dispute_id=dispute.id,
        sender_type=sender_type,
        message=payload.message,
    )
    db_session.add(msg)
    db_session.commit()
    db_session.refresh(dispute)
    return _dispute_out(dispute)


@dispute_apis.put("/{dispute_id}/resolve", response_model=DisputeOut)
def resolve_dispute(
    dispute_id: UUID,
    payload: ResolveDisputePayload,
    entity: PhoneVerification = Depends(auth_required),
):
    if entity.entity_type != "store":
        raise HTTPException(status_code=403, detail="Store access only")

    store = db_session.exec(select(Store).where(Store.entity_id == entity.id)).first()
    if not store:
        raise HTTPException(status_code=400, detail="Store profile not set")

    dispute = db_session.exec(
        select(Dispute).where(Dispute.id == dispute_id, Dispute.store_id == store.id)
    ).first()
    if not dispute:
        raise HTTPException(status_code=404, detail="Dispute not found")

    if payload.resolution not in DISPUTE_RESOLUTIONS:
        raise HTTPException(status_code=400, detail=f"Invalid resolution. Valid: {sorted(DISPUTE_RESOLUTIONS)}")

    dispute.status = "resolved"
    dispute.resolution = payload.resolution
    dispute.updated_at = datetime.utcnow()
    db_session.commit()
    db_session.refresh(dispute)
    return _dispute_out(dispute)


@dispute_apis.put("/{dispute_id}/close", response_model=DisputeOut)
def close_dispute(dispute_id: UUID, entity: PhoneVerification = Depends(auth_required)):
    if entity.entity_type != "user":
        raise HTTPException(status_code=403, detail="Shopper access only")

    user = db_session.exec(select(User).where(User.entity_id == entity.id)).first()
    if not user:
        raise HTTPException(status_code=400, detail="User profile not set")

    dispute = db_session.exec(
        select(Dispute).where(Dispute.id == dispute_id, Dispute.user_id == user.id)
    ).first()
    if not dispute:
        raise HTTPException(status_code=404, detail="Dispute not found")

    dispute.status = "closed"
    dispute.updated_at = datetime.utcnow()
    db_session.commit()
    db_session.refresh(dispute)
    return _dispute_out(dispute)


def _get_authorized_dispute(dispute_id: UUID, entity: PhoneVerification) -> Dispute:
    dispute = db_session.exec(select(Dispute).where(Dispute.id == dispute_id)).first()
    if not dispute:
        raise HTTPException(status_code=404, detail="Dispute not found")

    if entity.entity_type == "user":
        user = db_session.exec(select(User).where(User.entity_id == entity.id)).first()
        if not user or dispute.user_id != user.id:
            raise HTTPException(status_code=403, detail="Access denied")
    else:
        store = db_session.exec(select(Store).where(Store.entity_id == entity.id)).first()
        if not store or dispute.store_id != store.id:
            raise HTTPException(status_code=403, detail="Access denied")

    return dispute


def _dispute_out(dispute: Dispute) -> DisputeOut:
    messages = db_session.exec(
        select(DisputeMessage)
        .where(DisputeMessage.dispute_id == dispute.id)
        .order_by(DisputeMessage.created_at)
    ).all()

    return DisputeOut(
        id=dispute.id,
        order_id=dispute.order_id,
        store_id=dispute.store_id,
        reason=dispute.reason,
        description=dispute.description,
        status=dispute.status,
        resolution=dispute.resolution,
        created_at=dispute.created_at,
        updated_at=dispute.updated_at,
        messages=[
            DisputeMessageOut(
                id=m.id,
                sender_type=m.sender_type,
                message=m.message,
                created_at=m.created_at,
            )
            for m in messages
        ],
    )
