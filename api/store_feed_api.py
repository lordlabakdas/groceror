from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from pydantic import Field as PydanticField
from sqlmodel import func, select

from helpers.jwt import auth_required
from models.db import db_session
from models.entity.phone_verification import PhoneVerification
from models.entity.store_entity import Store
from models.entity.store_feed_post_entity import StoreFeedPost
from models.entity.user_entity import User
from models.service import store_feed_service, subscription_service

store_feed_apis = APIRouter(tags=["store-feed"])


async def _get_user(entity: PhoneVerification = Depends(auth_required)) -> User:
    user = db_session.exec(select(User).where(User.entity_id == entity.id)).first()
    if not user:
        raise HTTPException(status_code=400, detail="User profile not set")
    return user


async def _get_store(entity: PhoneVerification = Depends(auth_required)) -> Store:
    if entity.entity_type != "store":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Store access only"
        )
    store = db_session.exec(select(Store).where(Store.entity_id == entity.id)).first()
    if not store:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Store profile not set"
        )
    return store


async def _get_store_write(store: Store = Depends(_get_store)) -> Store:
    """Mutation-path variant of _get_store — 402s a billing-locked store."""
    subscription_service.assert_billing_ok(store)
    return store


class FeedItemResponse(BaseModel):
    id: UUID
    store_id: UUID
    store_name: str
    update_type: str
    message: str
    ref_id: Optional[UUID]
    created_at: datetime
    discount_label: Optional[str] = None
    coupon_code: Optional[str] = None
    expires_at: Optional[datetime] = None


class FeedResponse(BaseModel):
    items: List[FeedItemResponse]
    unread_count: int
    has_more: bool


class StorePostsResponse(BaseModel):
    items: List[FeedItemResponse]
    has_more: bool


class PostAnnouncementPayload(BaseModel):
    message: str = PydanticField(..., min_length=1, max_length=1000)


def _clamp_limit(limit: int) -> int:
    return max(1, min(limit, 100))


def _aware_utc(dt: datetime) -> datetime:
    """StoreFeedPost.created_at is stored naive-UTC (default_factory=datetime.utcnow).
    Left naive, Pydantic serializes it without a 'Z'/offset suffix and the
    frontend's `new Date(...)` parses that as local time — see the identical
    fix/rationale in flash_sale_api.py's _aware_utc."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


@store_feed_apis.get("/feed", response_model=FeedResponse)
async def get_feed(
    limit: int = Query(20),
    offset: int = Query(0, ge=0),
    user: User = Depends(_get_user),
):
    limit = _clamp_limit(limit)
    rows = store_feed_service.list_feed(user.id, limit=limit, offset=offset)
    total = store_feed_service.count_feed(user.id)
    items = [
        FeedItemResponse(
            id=row["post"].id,
            store_id=row["post"].store_id,
            store_name=row["store_name"],
            update_type=row["post"].update_type,
            message=row["post"].message,
            ref_id=row["post"].ref_id,
            created_at=_aware_utc(row["post"].created_at),
            discount_label=row.get("discount_label"),
            coupon_code=row.get("coupon_code"),
            expires_at=row.get("expires_at"),
        )
        for row in rows
    ]
    return FeedResponse(
        items=items,
        unread_count=store_feed_service.unread_count(user.id),
        has_more=offset + len(items) < total,
    )


@store_feed_apis.post("/feed/read", status_code=status.HTTP_204_NO_CONTENT)
async def mark_feed_read(user: User = Depends(_get_user)):
    store_feed_service.mark_read(user.id)


@store_feed_apis.post(
    "/stores/updates",
    response_model=FeedItemResponse,
    status_code=status.HTTP_201_CREATED,
)
async def post_announcement(
    payload: PostAnnouncementPayload, store: Store = Depends(_get_store_write)
):
    post = store_feed_service.emit_update(
        store.id, "announcement", payload.message.strip()
    )
    return FeedItemResponse(
        id=post.id,
        store_id=store.id,
        store_name=store.name,
        update_type=post.update_type,
        message=post.message,
        ref_id=post.ref_id,
        created_at=_aware_utc(post.created_at),
    )


@store_feed_apis.delete(
    "/stores/updates/{update_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_announcement(
    update_id: UUID, store: Store = Depends(_get_store_write)
):
    post = db_session.exec(
        select(StoreFeedPost).where(
            StoreFeedPost.id == update_id, StoreFeedPost.store_id == store.id
        )
    ).first()
    if not post:
        raise HTTPException(status_code=404, detail="Update not found")
    if post.update_type != "announcement":
        raise HTTPException(
            status_code=400, detail="Only manually posted announcements can be deleted"
        )
    db_session.delete(post)
    db_session.commit()


@store_feed_apis.get("/stores/{store_id}/updates", response_model=StorePostsResponse)
async def list_store_updates(
    store_id: UUID,
    limit: int = Query(20),
    offset: int = Query(0, ge=0),
    _: PhoneVerification = Depends(auth_required),
):
    limit = _clamp_limit(limit)
    store = db_session.exec(select(Store).where(Store.id == store_id)).first()
    if not store:
        raise HTTPException(status_code=404, detail="Store not found")

    posts = db_session.exec(
        select(StoreFeedPost)
        .where(StoreFeedPost.store_id == store_id)
        .order_by(StoreFeedPost.created_at.desc())
        .offset(offset)
        .limit(limit)
    ).all()
    total = db_session.exec(
        select(func.count())
        .select_from(StoreFeedPost)
        .where(StoreFeedPost.store_id == store_id)
    ).one()

    discounts = store_feed_service.enrich_discount_info(posts)
    items = [
        FeedItemResponse(
            id=p.id,
            store_id=store.id,
            store_name=store.name,
            update_type=p.update_type,
            message=p.message,
            ref_id=p.ref_id,
            created_at=_aware_utc(p.created_at),
            **discounts.get(p.id, {}),
        )
        for p in posts
    ]
    return StorePostsResponse(items=items, has_more=offset + len(items) < total)
