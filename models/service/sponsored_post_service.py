"""Sponsored posts business logic. See SPEC_SPONSORED_POSTS.md.

A SponsoredPost is created in status="pending" at checkout time (one
Razorpay Order, no money moved yet). confirm() is the only path that marks
it "paid" and — only then — calls store_feed_service.emit_update() to
create the StoreFeedPost that actually makes it visible in anyone's feed
(store_feed_service._feed_scope_filter treats update_type == "sponsored" as
visible to every shopper, not just followers). A failed/never-confirmed
payment never reaches emit_update, so it never reaches any feed.
"""
import logging
from datetime import datetime
from typing import List, Tuple
from uuid import UUID

from fastapi import HTTPException
from sqlmodel import select

from engine.billing import BillingProviderError, get_billing_provider
from models.db import db_session
from models.entity.sponsored_post_entity import SponsoredPost
from models.entity.sponsored_post_pricing_entity import SponsoredPostPricing
from models.entity.store_entity import Store
from models.entity.store_feed_post_entity import StoreFeedPost
from models.service import store_feed_service

logger = logging.getLogger(__name__)


def get_current_price() -> SponsoredPostPricing:
    """The current price — the most recently created SponsoredPostPricing
    row. The initial migration seeds one row (mirrors get_current_plan's
    SubscriptionPlan precedent), so this never returns None in practice."""
    price = db_session.exec(
        select(SponsoredPostPricing).order_by(SponsoredPostPricing.created_at.desc())
    ).first()
    if not price:
        raise HTTPException(status_code=500, detail="No sponsored post price configured")
    return price


def set_price(price_paise: int, created_by: str = "admin") -> SponsoredPostPricing:
    """Admin-facing. A pure DB write, same posture as
    subscription_service.set_plan_price — not retroactive, existing
    SponsoredPost rows keep whatever price was snapshotted onto them at
    their own checkout time."""
    if price_paise <= 0:
        raise HTTPException(status_code=400, detail="price_paise must be positive")
    price = SponsoredPostPricing(price_paise=price_paise, created_by=created_by)
    db_session.add(price)
    db_session.commit()
    db_session.refresh(price)
    return price


def create_pending(store: Store, message: str) -> SponsoredPost:
    """Store owner starts checkout. Resolves the current price and creates
    a one-time Razorpay Order — no StoreFeedPost yet, nothing visible to
    any shopper until confirm() succeeds."""
    price = get_current_price()
    try:
        order = get_billing_provider().create_order(price.price_paise)
    except BillingProviderError as e:
        raise HTTPException(status_code=502, detail=str(e))

    post = SponsoredPost(
        store_id=store.id,
        message=message,
        amount_paise=price.price_paise,
        razorpay_order_id=order.razorpay_order_id,
    )
    db_session.add(post)
    db_session.commit()
    db_session.refresh(post)
    return post


def _get_owned_pending(store_id: UUID, sponsored_post_id: UUID) -> SponsoredPost:
    post = db_session.exec(
        select(SponsoredPost).where(
            SponsoredPost.id == sponsored_post_id, SponsoredPost.store_id == store_id
        )
    ).first()
    if not post:
        raise HTTPException(status_code=404, detail="Sponsored post not found")
    return post


def confirm(
    store: Store, sponsored_post_id: UUID, payment_id: str, order_id: str, signature: str
) -> Tuple[SponsoredPost, StoreFeedPost]:
    """Verifies the Razorpay Checkout (Orders mode) success callback and,
    only on success, emits the StoreFeedPost that makes this post visible
    (SPEC_SPONSORED_POSTS.md §3.3). Idempotency guard: confirming an
    already-paid post 409s rather than double-posting to the feed."""
    post = _get_owned_pending(store.id, sponsored_post_id)
    if post.status == "paid":
        raise HTTPException(status_code=409, detail="This sponsored post has already been paid for")
    if post.razorpay_order_id != order_id:
        raise HTTPException(status_code=400, detail="Order id does not match this sponsored post")

    valid = get_billing_provider().verify_payment_signature(order_id, payment_id, signature)
    if not valid:
        post.status = "failed"
        db_session.add(post)
        db_session.commit()
        raise HTTPException(status_code=400, detail="Payment could not be verified")

    post.status = "paid"
    post.razorpay_payment_id = payment_id
    post.paid_at = datetime.utcnow()
    db_session.add(post)
    db_session.commit()
    db_session.refresh(post)

    feed_post = store_feed_service.emit_update(store.id, "sponsored", post.message, ref_id=post.id)

    post.feed_post_id = feed_post.id
    db_session.add(post)
    db_session.commit()
    db_session.refresh(post)

    return post, feed_post


def list_for_store(store_id: UUID) -> List[SponsoredPost]:
    return db_session.exec(
        select(SponsoredPost)
        .where(SponsoredPost.store_id == store_id)
        .order_by(SponsoredPost.created_at.desc())
    ).all()
