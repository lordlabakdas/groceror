"""Store follow feed business logic. See SPEC_STORE_FOLLOW_FEED.md.

emit_update() is the single write path for feed items — called both by the
manual "post an announcement" endpoint and, as a side effect, by the
existing coupon/promotion/flash-sale creation handlers. It fans the update
out over the existing SSE bus (api/sse_bus.py) to every follower's channel,
reusing the same in-app push mechanism already used for order/stock events
rather than adding a new one.
"""

from datetime import datetime, time, timezone
from typing import Dict, List, Optional
from uuid import UUID

from sqlmodel import func, or_, select

from api.sse_bus import publish as sse_publish
from models.db import db_session
from models.entity.coupon_entity import Coupon
from models.entity.feed_read_state_entity import FeedReadState
from models.entity.flash_sale_entity import FlashSale
from models.entity.promotion_entity import Promotion
from models.entity.store_entity import Store
from models.entity.store_feed_post_entity import StoreFeedPost
from models.entity.store_follow_entity import StoreFollow

UPDATE_TYPES = {"coupon", "promotion", "flash_sale", "announcement", "sponsored"}


def _discount_label(discount_type: str, discount_value: float) -> str:
    return (
        f"{discount_value:g}% off"
        if discount_type == "percent"
        else f"${discount_value:g} off"
    )


def enrich_discount_info(posts: List[StoreFeedPost]) -> Dict[UUID, dict]:
    """Per-post discount_label/coupon_code/expires_at for feed items that
    reference a Coupon/Promotion/FlashSale — batched by type rather than
    N+1 per post. Types without a ref (announcement, sponsored) or whose
    referenced row was since deleted just get no entry, so callers should
    `.get(post.id, {})` and let the response fields default to None."""
    by_type: Dict[str, List[UUID]] = {"coupon": [], "promotion": [], "flash_sale": []}
    for post in posts:
        if post.update_type in by_type and post.ref_id is not None:
            by_type[post.update_type].append(post.ref_id)

    info: Dict[UUID, dict] = {}

    if by_type["coupon"]:
        coupons = {
            c.id: c
            for c in db_session.exec(
                select(Coupon).where(Coupon.id.in_(by_type["coupon"]))
            ).all()
        }
        for post in posts:
            coupon = coupons.get(post.ref_id) if post.update_type == "coupon" else None
            if coupon:
                info[post.id] = {
                    "discount_label": _discount_label(
                        coupon.discount_type, coupon.discount_value
                    ),
                    "coupon_code": coupon.code,
                    "expires_at": None,
                }

    if by_type["promotion"]:
        promos = {
            p.id: p
            for p in db_session.exec(
                select(Promotion).where(Promotion.id.in_(by_type["promotion"]))
            ).all()
        }
        for post in posts:
            promo = promos.get(post.ref_id) if post.update_type == "promotion" else None
            if promo:
                info[post.id] = {
                    "discount_label": f"${promo.sale_price:g}",
                    "coupon_code": None,
                    "expires_at": datetime.combine(
                        promo.end_date, time.max, tzinfo=timezone.utc
                    ),
                }

    if by_type["flash_sale"]:
        sales = {
            s.id: s
            for s in db_session.exec(
                select(FlashSale).where(FlashSale.id.in_(by_type["flash_sale"]))
            ).all()
        }
        for post in posts:
            sale = sales.get(post.ref_id) if post.update_type == "flash_sale" else None
            if sale:
                end_at = (
                    sale.end_at
                    if sale.end_at.tzinfo is not None
                    else sale.end_at.replace(tzinfo=timezone.utc)
                )
                info[post.id] = {
                    "discount_label": f"${sale.sale_price:g}",
                    "coupon_code": None,
                    "expires_at": end_at,
                }

    return info


def _feed_scope_filter(user_id: UUID):
    """A shopper's feed is everything from a store they follow, PLUS every
    sponsored post platform-wide (SPEC_SPONSORED_POSTS.md §3.2) — a paid
    post reaches every shopper regardless of follow status. This one OR
    clause is the entire mechanism for that: no per-user fan-out insert,
    no broadcast job, just one more row every feed query already sees."""
    followed = select(StoreFollow.store_id).where(StoreFollow.user_id == user_id)
    return or_(
        StoreFeedPost.store_id.in_(followed), StoreFeedPost.update_type == "sponsored"
    )


def emit_update(
    store_id: UUID, update_type: str, message: str, ref_id: Optional[UUID] = None
) -> StoreFeedPost:
    post = StoreFeedPost(
        store_id=store_id, update_type=update_type, message=message, ref_id=ref_id
    )
    db_session.add(post)
    db_session.commit()
    db_session.refresh(post)
    _notify_followers(store_id, post)
    return post


def _notify_followers(store_id: UUID, post: StoreFeedPost) -> None:
    store = db_session.exec(select(Store).where(Store.id == store_id)).first()
    if not store:
        return
    follower_ids = db_session.exec(
        select(StoreFollow.user_id).where(StoreFollow.store_id == store_id)
    ).all()
    payload = {
        "store_id": str(store_id),
        "store_name": store.name,
        "update_type": post.update_type,
        "message": post.message,
    }
    for user_id in follower_ids:
        sse_publish(str(user_id), "store_update", payload)


def list_feed(user_id: UUID, limit: int, offset: int) -> List[dict]:
    """Reverse-chronological StoreFeedPost rows from stores the user follows,
    plus every sponsored post (see _feed_scope_filter)."""
    rows = db_session.exec(
        select(StoreFeedPost, Store.name)
        .join(Store, Store.id == StoreFeedPost.store_id)
        .where(_feed_scope_filter(user_id))
        .order_by(StoreFeedPost.created_at.desc())
        .offset(offset)
        .limit(limit)
    ).all()
    posts = [post for post, _ in rows]
    discounts = enrich_discount_info(posts)
    return [
        {"post": post, "store_name": store_name, **discounts.get(post.id, {})}
        for post, store_name in rows
    ]


def count_feed(user_id: UUID) -> int:
    return db_session.exec(
        select(func.count())
        .select_from(StoreFeedPost)
        .where(_feed_scope_filter(user_id))
    ).one()


def unread_count(user_id: UUID) -> int:
    state = db_session.exec(
        select(FeedReadState).where(FeedReadState.user_id == user_id)
    ).first()
    since = state.last_read_at if state else datetime.min
    return db_session.exec(
        select(func.count())
        .select_from(StoreFeedPost)
        .where(
            _feed_scope_filter(user_id),
            StoreFeedPost.created_at > since,
        )
    ).one()


def mark_read(user_id: UUID) -> None:
    state = db_session.exec(
        select(FeedReadState).where(FeedReadState.user_id == user_id)
    ).first()
    now = datetime.utcnow()
    if state:
        state.last_read_at = now
    else:
        state = FeedReadState(user_id=user_id, last_read_at=now)
        db_session.add(state)
    db_session.commit()
