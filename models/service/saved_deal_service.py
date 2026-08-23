"""Saved deals (My Deals) business logic. See SPEC_SAVED_DEALS.md.

A SavedDeal bookmarks a StoreFeedPost — only coupon/promotion/flash_sale
posts are saveable. StoreFeedPost rows are immutable history (never edited
or deleted, SPEC_STORE_FOLLOW_FEED.md §3), so freshness ("is this deal
still good?") is resolved from the *underlying* Coupon/Promotion/FlashSale
row every time the list is read, not stored on the SavedDeal itself.
"""
from dataclasses import dataclass
from datetime import date, datetime
from typing import List, Optional
from uuid import UUID

from sqlmodel import select

from models.db import db_session
from models.entity.coupon_entity import Coupon
from models.entity.flash_sale_entity import FlashSale
from models.entity.promotion_entity import Promotion
from models.entity.saved_deal_entity import SavedDeal
from models.entity.store_entity import Store
from models.entity.store_feed_post_entity import StoreFeedPost

SAVEABLE_TYPES = {"coupon", "promotion", "flash_sale"}


@dataclass
class SavedDealView:
    id: UUID
    feed_post_id: UUID
    update_type: str
    store_id: UUID
    store_name: str
    message: str
    status: str  # upcoming | active | expired
    expires_at: Optional[datetime]
    code: Optional[str]
    sale_price: Optional[float]
    saved_at: datetime


def _order_key(dt: datetime) -> float:
    """Monotonic sort key for a naive datetime, avoiding .timestamp()'s
    local-timezone assumption on naive values."""
    return (dt - datetime.min).total_seconds()


def _compute_coupon(coupon: Coupon) -> tuple:
    today = date.today()
    if coupon.valid_from and today < coupon.valid_from:
        stat = "upcoming"
    elif not coupon.is_active:
        stat = "expired"
    elif coupon.valid_until and today > coupon.valid_until:
        stat = "expired"
    elif coupon.max_uses is not None and coupon.uses_count >= coupon.max_uses:
        stat = "expired"
    else:
        stat = "active"
    expires_at = datetime.combine(coupon.valid_until, datetime.min.time()) if coupon.valid_until else None
    return stat, expires_at, coupon.code, None


def _compute_promotion(promo: Promotion) -> tuple:
    today = date.today()
    if today < promo.start_date:
        stat = "upcoming"
    elif today > promo.end_date:
        stat = "expired"
    else:
        stat = "active"
    expires_at = datetime.combine(promo.end_date, datetime.min.time())
    return stat, expires_at, None, promo.sale_price


def _compute_flash_sale(sale: FlashSale) -> tuple:
    now = datetime.utcnow()
    if now < sale.start_at:
        stat = "upcoming"
    elif not sale.is_active or now > sale.end_at:
        stat = "expired"
    else:
        stat = "active"
    return stat, sale.end_at, None, sale.sale_price


def _resolve(post: StoreFeedPost) -> Optional[tuple]:
    """Returns (status, expires_at, code, sale_price) or None if the
    source row this post referenced is gone."""
    if post.ref_id is None:
        return None
    if post.update_type == "coupon":
        source = db_session.exec(select(Coupon).where(Coupon.id == post.ref_id)).first()
        return _compute_coupon(source) if source else None
    if post.update_type == "promotion":
        source = db_session.exec(select(Promotion).where(Promotion.id == post.ref_id)).first()
        return _compute_promotion(source) if source else None
    if post.update_type == "flash_sale":
        source = db_session.exec(select(FlashSale).where(FlashSale.id == post.ref_id)).first()
        return _compute_flash_sale(source) if source else None
    return None


def save(user_id: UUID, feed_post_id: UUID) -> SavedDeal:
    """Idempotent — saving an already-saved post returns the existing row,
    matching wishlist_api.py's add_to_wishlist posture."""
    existing = db_session.exec(
        select(SavedDeal).where(SavedDeal.user_id == user_id, SavedDeal.feed_post_id == feed_post_id)
    ).first()
    if existing:
        return existing

    saved = SavedDeal(user_id=user_id, feed_post_id=feed_post_id)
    db_session.add(saved)
    db_session.commit()
    db_session.refresh(saved)
    return saved


def unsave(user_id: UUID, feed_post_id: UUID) -> None:
    existing = db_session.exec(
        select(SavedDeal).where(SavedDeal.user_id == user_id, SavedDeal.feed_post_id == feed_post_id)
    ).first()
    if existing:
        db_session.delete(existing)
        db_session.commit()


def is_saved(user_id: UUID, feed_post_id: UUID) -> bool:
    existing = db_session.exec(
        select(SavedDeal).where(SavedDeal.user_id == user_id, SavedDeal.feed_post_id == feed_post_id)
    ).first()
    return existing is not None


def _to_view(saved: SavedDeal, post: StoreFeedPost, store_name: str) -> Optional[SavedDealView]:
    resolved = _resolve(post)
    if resolved is None:
        return None
    stat, expires_at, code, sale_price = resolved
    return SavedDealView(
        id=saved.id,
        feed_post_id=post.id,
        update_type=post.update_type,
        store_id=post.store_id,
        store_name=store_name,
        message=post.message,
        status=stat,
        expires_at=expires_at,
        code=code,
        sale_price=sale_price,
        saved_at=saved.created_at,
    )


def get_view(user_id: UUID, feed_post_id: UUID) -> Optional[SavedDealView]:
    row = db_session.exec(
        select(SavedDeal, StoreFeedPost, Store.name)
        .join(StoreFeedPost, StoreFeedPost.id == SavedDeal.feed_post_id)
        .join(Store, Store.id == StoreFeedPost.store_id)
        .where(SavedDeal.user_id == user_id, SavedDeal.feed_post_id == feed_post_id)
    ).first()
    if not row:
        return None
    saved, post, store_name = row
    return _to_view(saved, post, store_name)


def list_for_user(user_id: UUID) -> List[SavedDealView]:
    rows = db_session.exec(
        select(SavedDeal, StoreFeedPost, Store.name)
        .join(StoreFeedPost, StoreFeedPost.id == SavedDeal.feed_post_id)
        .join(Store, Store.id == StoreFeedPost.store_id)
        .where(SavedDeal.user_id == user_id)
    ).all()

    views = [v for saved, post, store_name in rows if (v := _to_view(saved, post, store_name)) is not None]

    def sort_key(v: SavedDealView):
        if v.status == "expired":
            return (1, -_order_key(v.expires_at) if v.expires_at else 0.0)
        return (0, _order_key(v.expires_at) if v.expires_at else float("inf"))

    return sorted(views, key=sort_key)
