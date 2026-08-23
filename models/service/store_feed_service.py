"""Store follow feed business logic. See SPEC_STORE_FOLLOW_FEED.md.

emit_update() is the single write path for feed items — called both by the
manual "post an announcement" endpoint and, as a side effect, by the
existing coupon/promotion/flash-sale creation handlers. It fans the update
out over the existing SSE bus (api/sse_bus.py) to every follower's channel,
reusing the same in-app push mechanism already used for order/stock events
rather than adding a new one.
"""
from datetime import datetime
from typing import List, Optional
from uuid import UUID

from sqlmodel import or_, select, func

from api.sse_bus import publish as sse_publish
from models.db import db_session
from models.entity.feed_read_state_entity import FeedReadState
from models.entity.store_entity import Store
from models.entity.store_feed_post_entity import StoreFeedPost
from models.entity.store_follow_entity import StoreFollow

UPDATE_TYPES = {"coupon", "promotion", "flash_sale", "announcement", "sponsored"}


def _feed_scope_filter(user_id: UUID):
    """A shopper's feed is everything from a store they follow, PLUS every
    sponsored post platform-wide (SPEC_SPONSORED_POSTS.md §3.2) — a paid
    post reaches every shopper regardless of follow status. This one OR
    clause is the entire mechanism for that: no per-user fan-out insert,
    no broadcast job, just one more row every feed query already sees."""
    followed = select(StoreFollow.store_id).where(StoreFollow.user_id == user_id)
    return or_(StoreFeedPost.store_id.in_(followed), StoreFeedPost.update_type == "sponsored")


def emit_update(store_id: UUID, update_type: str, message: str, ref_id: Optional[UUID] = None) -> StoreFeedPost:
    post = StoreFeedPost(store_id=store_id, update_type=update_type, message=message, ref_id=ref_id)
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
    return [{"post": post, "store_name": store_name} for post, store_name in rows]


def count_feed(user_id: UUID) -> int:
    return db_session.exec(
        select(func.count()).select_from(StoreFeedPost).where(_feed_scope_filter(user_id))
    ).one()


def unread_count(user_id: UUID) -> int:
    state = db_session.exec(select(FeedReadState).where(FeedReadState.user_id == user_id)).first()
    since = state.last_read_at if state else datetime.min
    return db_session.exec(
        select(func.count()).select_from(StoreFeedPost).where(
            _feed_scope_filter(user_id),
            StoreFeedPost.created_at > since,
        )
    ).one()


def mark_read(user_id: UUID) -> None:
    state = db_session.exec(select(FeedReadState).where(FeedReadState.user_id == user_id)).first()
    now = datetime.utcnow()
    if state:
        state.last_read_at = now
    else:
        state = FeedReadState(user_id=user_id, last_read_at=now)
        db_session.add(state)
    db_session.commit()
