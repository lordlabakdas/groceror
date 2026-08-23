from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field as PydanticField
from sqlmodel import select

from config import AdminConfig, RazorpayConfig
from helpers.jwt import auth_required
from models.db import db_session
from models.entity.phone_verification import PhoneVerification
from models.entity.store_entity import Store
from models.service import sponsored_post_service, subscription_service

sponsored_post_apis = APIRouter(tags=["sponsored-posts"])


async def _get_store(entity: PhoneVerification = Depends(auth_required)) -> Store:
    if entity.entity_type != "store":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Store access only")
    store = db_session.exec(select(Store).where(Store.entity_id == entity.id)).first()
    if not store:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Store profile not set")
    return store


async def _get_store_write(store: Store = Depends(_get_store)) -> Store:
    """Mutation-path variant of _get_store — 402s a billing-locked store. A
    delinquent store can't buy a sponsored slot either. See
    SPEC_SPONSORED_POSTS.md §3.3."""
    subscription_service.assert_billing_ok(store)
    return store


async def _require_admin(x_admin_token: str = Header(...)):
    if x_admin_token != AdminConfig.ADMIN_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid admin token")


def _aware_utc(dt: datetime) -> datetime:
    """Stored naive-UTC — see the identical fix/rationale in
    flash_sale_api.py's and store_feed_api.py's _aware_utc."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


class CreateSponsoredPostPayload(BaseModel):
    message: str = PydanticField(..., min_length=1, max_length=1000)


class CreateSponsoredPostResponse(BaseModel):
    sponsored_post_id: UUID
    razorpay_order_id: str
    amount_paise: int
    razorpay_key_id: str


class ConfirmSponsoredPostPayload(BaseModel):
    razorpay_payment_id: str
    razorpay_order_id: str
    razorpay_signature: str


class FeedItemResponse(BaseModel):
    """Same shape as store_feed_api.py's FeedItemResponse — a confirmed
    sponsored post is just another feed item, update_type == "sponsored"."""

    id: UUID
    store_id: UUID
    store_name: str
    update_type: str
    message: str
    ref_id: Optional[UUID]
    created_at: datetime


class SponsoredPostSpendItem(BaseModel):
    id: UUID
    message: str
    amount_paise: int
    status: str
    created_at: datetime
    paid_at: Optional[datetime]


class SponsoredPostSpendResponse(BaseModel):
    items: List[SponsoredPostSpendItem]


class SponsoredPricingResponse(BaseModel):
    price_paise: int
    effective_since: datetime


class SetSponsoredPricingPayload(BaseModel):
    price_paise: int


@sponsored_post_apis.post("/stores/sponsored-posts", response_model=CreateSponsoredPostResponse, status_code=status.HTTP_201_CREATED)
async def create_sponsored_post(payload: CreateSponsoredPostPayload, store: Store = Depends(_get_store_write)):
    post = sponsored_post_service.create_pending(store, payload.message.strip())
    return CreateSponsoredPostResponse(
        sponsored_post_id=post.id,
        razorpay_order_id=post.razorpay_order_id,
        amount_paise=post.amount_paise,
        razorpay_key_id=RazorpayConfig.KEY_ID,
    )


@sponsored_post_apis.post("/stores/sponsored-posts/{sponsored_post_id}/confirm", response_model=FeedItemResponse)
async def confirm_sponsored_post(
    sponsored_post_id: UUID,
    payload: ConfirmSponsoredPostPayload,
    store: Store = Depends(_get_store),
):
    _post, feed_post = sponsored_post_service.confirm(
        store,
        sponsored_post_id,
        payload.razorpay_payment_id,
        payload.razorpay_order_id,
        payload.razorpay_signature,
    )
    return FeedItemResponse(
        id=feed_post.id,
        store_id=store.id,
        store_name=store.name,
        update_type=feed_post.update_type,
        message=feed_post.message,
        ref_id=feed_post.ref_id,
        created_at=_aware_utc(feed_post.created_at),
    )


@sponsored_post_apis.get("/stores/sponsored-posts", response_model=SponsoredPostSpendResponse)
async def list_sponsored_posts(store: Store = Depends(_get_store)):
    posts = sponsored_post_service.list_for_store(store.id)
    return SponsoredPostSpendResponse(
        items=[
            SponsoredPostSpendItem(
                id=p.id,
                message=p.message,
                amount_paise=p.amount_paise,
                status=p.status,
                created_at=_aware_utc(p.created_at),
                paid_at=_aware_utc(p.paid_at) if p.paid_at else None,
            )
            for p in posts
        ]
    )


@sponsored_post_apis.get("/sponsored-posts/admin/price", response_model=SponsoredPricingResponse, dependencies=[Depends(_require_admin)])
async def get_sponsored_price():
    price = sponsored_post_service.get_current_price()
    return SponsoredPricingResponse(price_paise=price.price_paise, effective_since=price.created_at)


@sponsored_post_apis.post("/sponsored-posts/admin/price", response_model=SponsoredPricingResponse, dependencies=[Depends(_require_admin)])
async def set_sponsored_price(payload: SetSponsoredPricingPayload):
    price = sponsored_post_service.set_price(payload.price_paise)
    return SponsoredPricingResponse(price_paise=price.price_paise, effective_since=price.created_at)
