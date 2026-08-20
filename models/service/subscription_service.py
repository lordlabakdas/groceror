"""Subscription billing business logic. See SPEC_SUBSCRIPTION.md.

State machine (§3.2):
    trialing -> active     (Razorpay reports the first charge)
    trialing -> grace      (trial_end passes, never checked out)
    active   -> grace      (payment fails / Razorpay reports pending)
    grace    -> active     (payment succeeds)
    grace    -> locked     (grace_period_end passes unresolved)
    locked   -> active     (payment succeeds)
    any      -> cancelled  (owner or admin cancels)

Transitions come from two places: real-time Razorpay webhooks
(`apply_webhook`), and a lazy check on every read (`_recompute_status`) that
catches the two time-based transitions webhooks can't drive on their own
(trial lapsing unauthorized, grace period expiring) — no cron/scheduler,
per constitution Principle VI (monolith simplicity, no speculative infra).
"""

import logging
from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID

from fastapi import HTTPException, status
from sqlmodel import select

from engine.billing import (
    BillingProviderError,
    SubscriptionWebhookEvent,
    get_billing_provider,
)
from engine.mailer import Mailer
from models.db import db_session
from models.entity.store_entity import Store
from models.entity.subscription_entity import Subscription
from models.entity.subscription_invoice_entity import SubscriptionInvoice
from models.entity.subscription_plan_entity import SubscriptionPlan

logger = logging.getLogger(__name__)

# Proposed defaults — SPEC_SUBSCRIPTION.md §1. Constants, not schema: change
# here, not via migration. (Plan *price* is DB-backed and admin-editable,
# §3.1/§3.5 — these two are not, since changing them retroactively for an
# in-flight trial/grace period would be a much bigger behavior change.)
TRIAL_DAYS = 14
GRACE_DAYS = 7

_ACTIVE_EVENTS = {"subscription.authenticated", "subscription.activated", "subscription.charged"}
_GRACE_EVENTS = {"subscription.pending", "subscription.halted"}


def get_current_plan() -> SubscriptionPlan:
    """The current price — the most recently created SubscriptionPlan row.
    The initial migration seeds one row, so this never returns None in
    practice, but a fresh test DB with no seed data could hit an empty
    table, hence the explicit error rather than an AttributeError later."""
    plan = db_session.exec(
        select(SubscriptionPlan).order_by(SubscriptionPlan.created_at.desc())
    ).first()
    if not plan:
        raise HTTPException(status_code=500, detail="No subscription plan configured")
    return plan


def set_plan_price(price_paise: int, created_by: str = "admin") -> SubscriptionPlan:
    """Admin-facing (§3.5). A pure DB write — deliberately doesn't call
    Razorpay here, so an admin price change can't fail because Razorpay
    happens to be down. The Razorpay Plan for this price is created lazily,
    on first checkout at this price (see _resolve_razorpay_plan_id).
    Not retroactive: existing Subscription rows keep whatever price was
    snapshotted onto them at their own checkout time."""
    if price_paise <= 0:
        raise HTTPException(status_code=400, detail="price_paise must be positive")
    plan = SubscriptionPlan(price_paise=price_paise, created_by=created_by)
    db_session.add(plan)
    db_session.commit()
    db_session.refresh(plan)
    return plan


def _resolve_razorpay_plan_id(plan: SubscriptionPlan) -> str:
    if plan.razorpay_plan_id:
        return plan.razorpay_plan_id
    plan_id = get_billing_provider().create_plan(plan.price_paise)
    plan.razorpay_plan_id = plan_id
    db_session.add(plan)
    db_session.commit()
    db_session.refresh(plan)
    return plan_id


def create_trial_subscription(store_id: UUID) -> Subscription:
    """Called from StoreService.create_store() right after the store row
    commits — every store gets a trial immediately, no separate signup
    step (§3.2). No card required, no Razorpay objects created yet."""
    sub = Subscription(
        store_id=store_id,
        status="trialing",
        trial_end=datetime.utcnow() + timedelta(days=TRIAL_DAYS),
    )
    db_session.add(sub)
    db_session.commit()
    db_session.refresh(sub)
    return sub


def _get_subscription(store_id: UUID) -> Subscription:
    """Self-healing: a store can end up without a Subscription row despite
    §3.2's intent — StoreService.create_store() isn't the only place a
    Store gets created (e.g. api/helpers/auth_helper.py's
    set_store_profile()), and any store that existed before this feature
    shipped predates the row entirely. Rather than track down every call
    site (present and future), lazily back-fill a trial here instead of
    404ing — the store simply gets a fresh trial starting from whenever
    its subscription is first checked."""
    sub = db_session.exec(select(Subscription).where(Subscription.store_id == store_id)).first()
    if not sub:
        sub = create_trial_subscription(store_id)
    return sub


def _sync_store_lock(store_id: UUID, locked: bool) -> None:
    store = db_session.exec(select(Store).where(Store.id == store_id)).first()
    if store and store.is_billing_locked != locked:
        store.is_billing_locked = locked
        store.updated_at = datetime.utcnow()
        db_session.add(store)
        db_session.commit()


def _send_grace_email(sub: Subscription) -> None:
    """Principle V: a Resend outage must not block the state transition
    that triggered this. One email on entering grace, not a sequence
    (Out of Scope, SPEC_SUBSCRIPTION.md §8)."""
    store = db_session.exec(select(Store).where(Store.id == sub.store_id)).first()
    if not store:
        return
    try:
        Mailer().send(
            recipient=store.email,
            subject="Action needed: your Groceror subscription payment",
            body=(
                f"Hi {store.name},\n\n"
                "We weren't able to process your Groceror subscription payment "
                f"(or your trial has ended without a payment method on file). "
                f"You have until {sub.grace_period_end:%Y-%m-%d} to resolve this "
                "from your Billing page before your storefront goes offline to "
                "shoppers.\n\nThank you for being a Groceror store owner!"
            ),
        )
    except Exception:
        logger.exception("Failed to send grace-period email for store_id=%s", sub.store_id)


def _enter_grace(sub: Subscription) -> None:
    if sub.status == "grace":
        return  # already in grace — don't reset the clock or re-send the email
    sub.status = "grace"
    sub.grace_period_end = datetime.utcnow() + timedelta(days=GRACE_DAYS)
    sub.updated_at = datetime.utcnow()
    db_session.add(sub)
    db_session.commit()
    db_session.refresh(sub)
    _send_grace_email(sub)


def _recompute_status(sub: Subscription) -> Subscription:
    now = datetime.utcnow()
    if sub.status == "trialing" and now > sub.trial_end and not sub.razorpay_subscription_id:
        # Trial lapsed with no checkout ever attempted.
        _enter_grace(sub)
    elif sub.status == "grace" and sub.grace_period_end and now > sub.grace_period_end:
        sub.status = "locked"
        sub.updated_at = now
        db_session.add(sub)
        db_session.commit()
        db_session.refresh(sub)

    _sync_store_lock(sub.store_id, locked=(sub.status == "locked"))
    return sub


def get_status_for_store(store_id: UUID) -> Subscription:
    return _recompute_status(_get_subscription(store_id))


def assert_billing_ok(store: Store) -> None:
    """Gate for mutation endpoints (§3.3). Read endpoints don't call this —
    a locked owner must still be able to see their data and reach billing."""
    sub = get_status_for_store(store.id)
    if sub.status == "locked":
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Your Groceror subscription payment is past due. Visit Billing to resolve it.",
        )


def checkout(store: Store) -> Subscription:
    """Store owner initiates/resumes payment setup (§3.4). Resolves the
    current plan (creating its Razorpay Plan if not yet cached), creates a
    Razorpay customer if needed, and creates a Razorpay subscription whose
    first charge is delayed to trial_end (or now, if the trial's already
    over). Snapshots plan_price_paise onto this store's Subscription at
    this moment — later admin price changes don't retroactively affect it."""
    sub = _get_subscription(store.id)
    if sub.razorpay_subscription_id:
        return sub  # already checked out — idempotent

    plan = get_current_plan()
    try:
        razorpay_plan_id = _resolve_razorpay_plan_id(plan)
        provider = get_billing_provider()
        if not sub.razorpay_customer_id:
            customer = provider.create_customer(
                name=store.name, email=store.email, contact=store.email
            )
            sub.razorpay_customer_id = customer.razorpay_customer_id

        start_at = max(sub.trial_end, datetime.utcnow())
        subscription = provider.create_subscription(
            razorpay_plan_id, sub.razorpay_customer_id, start_at
        )
    except BillingProviderError as e:
        raise HTTPException(status_code=502, detail=str(e))

    sub.razorpay_subscription_id = subscription.razorpay_subscription_id
    sub.plan_price_paise = plan.price_paise
    sub.updated_at = datetime.utcnow()
    db_session.add(sub)
    db_session.commit()
    db_session.refresh(sub)
    return sub


def cancel(store: Store) -> Subscription:
    sub = _get_subscription(store.id)
    if sub.razorpay_subscription_id:
        try:
            get_billing_provider().cancel_subscription(sub.razorpay_subscription_id)
        except BillingProviderError:
            logger.exception("Razorpay cancel failed for store_id=%s — cancelling locally anyway", store.id)
    sub.status = "cancelled"
    sub.cancelled_at = datetime.utcnow()
    sub.updated_at = datetime.utcnow()
    db_session.add(sub)
    db_session.commit()
    db_session.refresh(sub)
    return sub


def apply_webhook(event: SubscriptionWebhookEvent) -> Optional[Subscription]:
    """Returns None if no Subscription matches — the webhook route acks
    200 anyway so Razorpay doesn't retry forever (mirrors
    api/webhook_api.py's Shiprocket handling of unknown ids)."""
    sub = db_session.exec(
        select(Subscription).where(Subscription.razorpay_subscription_id == event.razorpay_subscription_id)
    ).first()
    if not sub:
        logger.warning("Webhook for unknown razorpay_subscription_id=%s", event.razorpay_subscription_id)
        return None

    if event.event in _ACTIVE_EVENTS:
        sub.status = "active"
        if event.current_period_start:
            sub.current_period_start = event.current_period_start
        if event.current_period_end:
            sub.current_period_end = event.current_period_end
        sub.updated_at = datetime.utcnow()
        db_session.add(sub)
        db_session.commit()
        db_session.refresh(sub)

        if event.event == "subscription.charged" and event.amount_paise is not None:
            invoice = SubscriptionInvoice(
                subscription_id=sub.id,
                razorpay_payment_id=event.razorpay_payment_id,
                amount_paise=event.amount_paise,
                status="paid",
                period_start=event.current_period_start or datetime.utcnow(),
                period_end=event.current_period_end or (datetime.utcnow() + timedelta(days=30)),
                paid_at=datetime.utcnow(),
            )
            db_session.add(invoice)
            db_session.commit()

        _sync_store_lock(sub.store_id, locked=False)

    elif event.event in _GRACE_EVENTS:
        _enter_grace(sub)

    elif event.event == "subscription.cancelled":
        sub.status = "cancelled"
        sub.cancelled_at = datetime.utcnow()
        sub.updated_at = datetime.utcnow()
        db_session.add(sub)
        db_session.commit()
        db_session.refresh(sub)

    return sub


def list_invoices(store_id: UUID) -> list[SubscriptionInvoice]:
    sub = _get_subscription(store_id)
    return db_session.exec(
        select(SubscriptionInvoice)
        .where(SubscriptionInvoice.subscription_id == sub.id)
        .order_by(SubscriptionInvoice.created_at.desc())
    ).all()


def admin_list() -> dict:
    rows = db_session.exec(select(Subscription, Store).where(Subscription.store_id == Store.id)).all()
    subscriptions = [
        {
            "store_id": store.id,
            "store_name": store.name,
            "status": sub.status,
            "plan_price_paise": sub.plan_price_paise,
            "current_period_end": sub.current_period_end,
        }
        for sub, store in rows
    ]
    mrr_paise = sum(sub.plan_price_paise or 0 for sub, _ in rows if sub.status == "active")
    return {"subscriptions": subscriptions, "mrr_paise": mrr_paise}


def admin_unlock(store_id: UUID) -> Subscription:
    """Manual goodwill/support override (§3.5) — bypasses Razorpay
    entirely. The next real webhook still updates state normally
    afterward."""
    sub = _get_subscription(store_id)
    sub.status = "active"
    sub.current_period_end = datetime.utcnow() + timedelta(days=30)
    sub.updated_at = datetime.utcnow()
    db_session.add(sub)
    db_session.commit()
    db_session.refresh(sub)
    _sync_store_lock(store_id, locked=False)
    return sub
