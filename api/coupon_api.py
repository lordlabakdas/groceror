import logging
from datetime import date, datetime
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field as PydanticField
from sqlmodel import select

from helpers.jwt import auth_required
from models.db import db_session
from models.entity.coupon_entity import Coupon
from models.entity.phone_verification import PhoneVerification
from models.entity.store_entity import Store

logger = logging.getLogger(__name__)
coupon_apis = APIRouter(prefix="/coupons", tags=["coupons"])


def _get_store(entity: PhoneVerification = Depends(auth_required)) -> Store:
    if entity.entity_type != "store":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Store access only")
    store = db_session.exec(select(Store).where(Store.entity_id == entity.id)).first()
    if not store:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Store profile not set")
    return store


class CreateCouponPayload(BaseModel):
    code: str
    discount_type: str = PydanticField(..., pattern="^(percent|fixed)$")
    discount_value: float = PydanticField(..., gt=0)
    min_order_amount: Optional[float] = None
    max_uses: Optional[int] = None
    valid_from: Optional[date] = None
    valid_until: Optional[date] = None


class CouponResponse(BaseModel):
    id: UUID
    code: str
    discount_type: str
    discount_value: float
    min_order_amount: Optional[float]
    max_uses: Optional[int]
    uses_count: int
    store_id: Optional[UUID]
    valid_from: Optional[date]
    valid_until: Optional[date]
    is_active: bool
    created_at: datetime


class ValidateCouponResponse(BaseModel):
    valid: bool
    discount_type: str
    discount_value: float
    discount_amount: float
    message: str


@coupon_apis.post("", response_model=CouponResponse, status_code=status.HTTP_201_CREATED)
async def create_coupon(payload: CreateCouponPayload, store: Store = Depends(_get_store)):
    code = payload.code.strip().upper()
    if not code:
        raise HTTPException(status_code=400, detail="Coupon code cannot be empty")
    if payload.valid_from and payload.valid_until and payload.valid_from > payload.valid_until:
        raise HTTPException(status_code=400, detail="valid_from must be before valid_until")
    if payload.discount_type == "percent" and payload.discount_value > 100:
        raise HTTPException(status_code=400, detail="Percent discount cannot exceed 100")

    existing = db_session.exec(select(Coupon).where(Coupon.code == code)).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"Coupon code '{code}' already exists")

    coupon = Coupon(
        code=code,
        discount_type=payload.discount_type,
        discount_value=payload.discount_value,
        min_order_amount=payload.min_order_amount,
        max_uses=payload.max_uses,
        store_id=store.id,
        valid_from=payload.valid_from,
        valid_until=payload.valid_until,
    )
    db_session.add(coupon)
    db_session.commit()
    db_session.refresh(coupon)
    return coupon


@coupon_apis.get("", response_model=List[CouponResponse])
async def list_coupons(store: Store = Depends(_get_store)):
    coupons = db_session.exec(
        select(Coupon).where(Coupon.store_id == store.id).order_by(Coupon.created_at.desc())
    ).all()
    return coupons


@coupon_apis.delete("/{code}", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_coupon(code: str, store: Store = Depends(_get_store)):
    coupon = db_session.exec(
        select(Coupon).where(Coupon.code == code.upper(), Coupon.store_id == store.id)
    ).first()
    if not coupon:
        raise HTTPException(status_code=404, detail="Coupon not found")
    coupon.is_active = False
    coupon.updated_at = datetime.utcnow()
    db_session.commit()


@coupon_apis.get("/{code}/validate", response_model=ValidateCouponResponse)
async def validate_coupon(code: str, order_total: float = 0.0, _: PhoneVerification = Depends(auth_required)):
    coupon = db_session.exec(select(Coupon).where(Coupon.code == code.upper())).first()
    if not coupon or not coupon.is_active:
        return ValidateCouponResponse(
            valid=False, discount_type="fixed", discount_value=0, discount_amount=0,
            message="Coupon not found or inactive"
        )
    today = date.today()
    if coupon.valid_from and today < coupon.valid_from:
        return ValidateCouponResponse(
            valid=False, discount_type=coupon.discount_type, discount_value=coupon.discount_value,
            discount_amount=0, message="Coupon is not yet active"
        )
    if coupon.valid_until and today > coupon.valid_until:
        return ValidateCouponResponse(
            valid=False, discount_type=coupon.discount_type, discount_value=coupon.discount_value,
            discount_amount=0, message="Coupon has expired"
        )
    if coupon.max_uses is not None and coupon.uses_count >= coupon.max_uses:
        return ValidateCouponResponse(
            valid=False, discount_type=coupon.discount_type, discount_value=coupon.discount_value,
            discount_amount=0, message="Coupon has reached its usage limit"
        )
    if coupon.min_order_amount and order_total < coupon.min_order_amount:
        return ValidateCouponResponse(
            valid=False, discount_type=coupon.discount_type, discount_value=coupon.discount_value,
            discount_amount=0,
            message=f"Minimum order of ${coupon.min_order_amount:.2f} required"
        )

    if coupon.discount_type == "percent":
        discount_amount = round(order_total * coupon.discount_value / 100, 2)
    else:
        discount_amount = min(coupon.discount_value, order_total)

    return ValidateCouponResponse(
        valid=True,
        discount_type=coupon.discount_type,
        discount_value=coupon.discount_value,
        discount_amount=discount_amount,
        message=f"Coupon valid — saves ${discount_amount:.2f}",
    )
