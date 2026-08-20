import logging
from datetime import datetime
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel
from sqlmodel import select

from config import AdminConfig, RazorpayConfig
from helpers.jwt import auth_required
from models.db import db_session
from models.entity.phone_verification import PhoneVerification
from models.entity.store_entity import Store
from models.service import subscription_service

logger = logging.getLogger(__name__)
subscription_apis = APIRouter(prefix="/subscription", tags=["subscription"])


def _get_store(entity: PhoneVerification = Depends(auth_required)) -> Store:
    if entity.entity_type != "store":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Store access only")
    store = db_session.exec(select(Store).where(Store.entity_id == entity.id)).first()
    if not store:
        raise HTTPException(status_code=400, detail="Store profile not set")
    return store


async def _require_admin(x_admin_token: str = Header(...)):
    if x_admin_token != AdminConfig.ADMIN_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid admin token")


class SubscriptionStatusResponse(BaseModel):
    status: str
    plan_price_paise: int
    trial_end: datetime
    current_period_end: Optional[datetime]
    grace_period_end: Optional[datetime]
    razorpay_subscription_id: Optional[str]
    checkout_needed: bool


class CheckoutResponse(BaseModel):
    razorpay_subscription_id: str
    razorpay_key_id: str


class CancelResponse(BaseModel):
    status: str
    effective_at: Optional[datetime]


class AdminSubscriptionRow(BaseModel):
    store_id: UUID
    store_name: str
    status: str
    plan_price_paise: Optional[int]
    current_period_end: Optional[datetime]


class AdminListResponse(BaseModel):
    subscriptions: List[AdminSubscriptionRow]
    mrr_paise: int


class PlanPriceResponse(BaseModel):
    price_paise: int
    effective_since: datetime


class SetPlanPricePayload(BaseModel):
    price_paise: int


@subscription_apis.get("/status", response_model=SubscriptionStatusResponse)
async def get_status(store: Store = Depends(_get_store)):
    sub = subscription_service.get_status_for_store(store.id)
    # Before checkout, show the *current* plan price as a preview — nothing
    # charged yet, so it tracks live admin price changes (§3.1).
    price_paise = sub.plan_price_paise or subscription_service.get_current_plan().price_paise
    return SubscriptionStatusResponse(
        status=sub.status,
        plan_price_paise=price_paise,
        trial_end=sub.trial_end,
        current_period_end=sub.current_period_end,
        grace_period_end=sub.grace_period_end,
        razorpay_subscription_id=sub.razorpay_subscription_id,
        checkout_needed=sub.razorpay_subscription_id is None and sub.status != "cancelled",
    )


@subscription_apis.post("/checkout", response_model=CheckoutResponse)
async def start_checkout(store: Store = Depends(_get_store)):
    sub = subscription_service.checkout(store)
    return CheckoutResponse(
        razorpay_subscription_id=sub.razorpay_subscription_id,
        razorpay_key_id=RazorpayConfig.KEY_ID,
    )


@subscription_apis.post("/cancel", response_model=CancelResponse)
async def cancel_subscription(store: Store = Depends(_get_store)):
    sub = subscription_service.cancel(store)
    return CancelResponse(status=sub.status, effective_at=sub.current_period_end)


@subscription_apis.get("/admin/list", response_model=AdminListResponse, dependencies=[Depends(_require_admin)])
async def admin_list_subscriptions():
    return subscription_service.admin_list()


@subscription_apis.post(
    "/{store_id}/admin/unlock",
    response_model=SubscriptionStatusResponse,
    dependencies=[Depends(_require_admin)],
)
async def admin_unlock_store(store_id: UUID):
    sub = subscription_service.admin_unlock(store_id)
    return SubscriptionStatusResponse(
        status=sub.status,
        plan_price_paise=sub.plan_price_paise or subscription_service.get_current_plan().price_paise,
        trial_end=sub.trial_end,
        current_period_end=sub.current_period_end,
        grace_period_end=sub.grace_period_end,
        razorpay_subscription_id=sub.razorpay_subscription_id,
        checkout_needed=sub.razorpay_subscription_id is None,
    )


@subscription_apis.get("/admin/plan-price", response_model=PlanPriceResponse, dependencies=[Depends(_require_admin)])
async def get_plan_price():
    plan = subscription_service.get_current_plan()
    return PlanPriceResponse(price_paise=plan.price_paise, effective_since=plan.created_at)


@subscription_apis.post("/admin/plan-price", response_model=PlanPriceResponse, dependencies=[Depends(_require_admin)])
async def set_plan_price(payload: SetPlanPricePayload):
    plan = subscription_service.set_plan_price(payload.price_paise)
    return PlanPriceResponse(price_paise=plan.price_paise, effective_since=plan.created_at)
