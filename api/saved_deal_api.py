from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlmodel import select

from helpers.jwt import auth_required
from models.db import db_session
from models.entity.phone_verification import PhoneVerification
from models.entity.store_feed_post_entity import StoreFeedPost
from models.entity.user_entity import User
from models.service import saved_deal_service

saved_deal_apis = APIRouter(tags=["saved-deals"])


async def _get_user(entity: PhoneVerification = Depends(auth_required)) -> User:
    user = db_session.exec(select(User).where(User.entity_id == entity.id)).first()
    if not user:
        raise HTTPException(status_code=400, detail="User profile not set")
    return user


def _aware_utc(dt: datetime) -> datetime:
    """Stored naive-UTC — see the identical fix/rationale in
    flash_sale_api.py's and store_feed_api.py's _aware_utc."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


class SavedDealResponse(BaseModel):
    id: UUID
    feed_post_id: UUID
    update_type: str
    store_id: UUID
    store_name: str
    message: str
    status: str
    expires_at: Optional[datetime]
    code: Optional[str]
    sale_price: Optional[float]
    saved_at: datetime


class MyDealsResponse(BaseModel):
    items: List[SavedDealResponse]


def _to_response(view) -> SavedDealResponse:
    return SavedDealResponse(
        id=view.id,
        feed_post_id=view.feed_post_id,
        update_type=view.update_type,
        store_id=view.store_id,
        store_name=view.store_name,
        message=view.message,
        status=view.status,
        expires_at=_aware_utc(view.expires_at) if view.expires_at else None,
        code=view.code,
        sale_price=view.sale_price,
        saved_at=_aware_utc(view.saved_at),
    )


@saved_deal_apis.post("/feed/{feed_post_id}/save", response_model=SavedDealResponse, status_code=status.HTTP_201_CREATED)
async def save_deal(feed_post_id: UUID, user: User = Depends(_get_user)):
    post = db_session.exec(select(StoreFeedPost).where(StoreFeedPost.id == feed_post_id)).first()
    if not post:
        raise HTTPException(status_code=404, detail="Feed post not found")
    if post.update_type not in saved_deal_service.SAVEABLE_TYPES:
        raise HTTPException(status_code=400, detail="Only coupon, promotion, and flash_sale posts can be saved")

    saved_deal_service.save(user.id, feed_post_id)
    view = saved_deal_service.get_view(user.id, feed_post_id)
    if view is None:
        # The underlying Coupon/Promotion/FlashSale row is gone the moment
        # after saving — practically unreachable (none of the three are
        # ever hard-deleted), but fail clearly rather than 500 on a None.
        raise HTTPException(status_code=404, detail="This deal is no longer available")
    return _to_response(view)


@saved_deal_apis.delete("/feed/{feed_post_id}/save", status_code=status.HTTP_204_NO_CONTENT)
async def unsave_deal(feed_post_id: UUID, user: User = Depends(_get_user)):
    saved_deal_service.unsave(user.id, feed_post_id)


@saved_deal_apis.get("/feed/{feed_post_id}/saved", response_model=bool)
async def check_saved(feed_post_id: UUID, user: User = Depends(_get_user)):
    return saved_deal_service.is_saved(user.id, feed_post_id)


@saved_deal_apis.get("/my-deals", response_model=MyDealsResponse)
async def list_my_deals(user: User = Depends(_get_user)):
    views = saved_deal_service.list_for_user(user.id)
    return MyDealsResponse(items=[_to_response(v) for v in views])
