"""Razorpay Subscriptions BillingProvider implementation.

UNVERIFIED: the Razorpay SDK call shapes, webhook event names/payload, and
signature-verification mechanism below are assumed from general knowledge of
Razorpay's Subscriptions product, not a transcription of their current docs
or a real test account — the same posture SPEC_DELIVERY_DISPATCH.md took
with Shiprocket Quick before that integration was confirmed. Per
SPEC_SUBSCRIPTION.md's Implementation Order, the first real implementation
task is a Razorpay test account and reconciling this against actual
responses. Nothing in the test suite exercises this class — tests use
FakeBillingProvider instead (constitution Principle II).
"""

import logging
from datetime import datetime

import razorpay

from config import RazorpayConfig
from engine.billing.provider import (
    BillingProviderError,
    RazorpayCustomer,
    RazorpayOrder,
    RazorpaySubscription,
    SubscriptionWebhookEvent,
)

logger = logging.getLogger(__name__)

# Razorpay plans/subscriptions are monthly (period="monthly", interval=1) —
# matches the single-flat-plan decision in SPEC_SUBSCRIPTION.md §1.
_PLAN_PERIOD = "monthly"
_PLAN_INTERVAL = 1
# Razorpay subscriptions need a total_count of billing cycles up front;
# there's no "until cancelled" option. A large count approximates that —
# cancellation is a separate explicit call (cancel_subscription), not
# reaching total_count.
_TOTAL_BILLING_CYCLES = 1200  # 100 years of monthly cycles


class RazorpayProvider:
    def __init__(self):
        self._client = razorpay.Client(
            auth=(RazorpayConfig.KEY_ID, RazorpayConfig.KEY_SECRET)
        )

    def create_plan(self, price_paise: int) -> str:
        try:
            plan = self._client.plan.create(
                {
                    "period": _PLAN_PERIOD,
                    "interval": _PLAN_INTERVAL,
                    "item": {
                        "name": "Groceror Store Subscription",
                        "amount": price_paise,
                        "currency": "INR",
                    },
                }
            )
        except Exception as e:
            raise BillingProviderError(f"Failed to create Razorpay plan: {e}")
        return plan["id"]

    def create_customer(self, name: str, email: str, contact: str) -> RazorpayCustomer:
        try:
            customer = self._client.customer.create(
                {"name": name, "email": email, "contact": contact}
            )
        except Exception as e:
            raise BillingProviderError(f"Failed to create Razorpay customer: {e}")
        return RazorpayCustomer(razorpay_customer_id=customer["id"])

    def create_subscription(
        self, plan_id: str, customer_id: str, start_at: datetime
    ) -> RazorpaySubscription:
        try:
            subscription = self._client.subscription.create(
                {
                    "plan_id": plan_id,
                    "customer_notify": 1,
                    "total_count": _TOTAL_BILLING_CYCLES,
                    "start_at": int(start_at.timestamp()),
                    "notes": {"razorpay_customer_id": customer_id},
                }
            )
        except Exception as e:
            raise BillingProviderError(f"Failed to create Razorpay subscription: {e}")
        return RazorpaySubscription(razorpay_subscription_id=subscription["id"])

    def cancel_subscription(self, subscription_id: str) -> None:
        try:
            self._client.subscription.cancel(subscription_id, {"cancel_at_cycle_end": 1})
        except Exception as e:
            logger.warning("Razorpay subscription cancel failed for %s: %s", subscription_id, e)
            raise BillingProviderError(f"Failed to cancel Razorpay subscription: {e}")

    def verify_webhook_signature(self, raw_body: bytes, signature: str | None) -> bool:
        if not signature or not RazorpayConfig.WEBHOOK_SECRET:
            return False
        try:
            self._client.utility.verify_webhook_signature(
                raw_body.decode(), signature, RazorpayConfig.WEBHOOK_SECRET
            )
            return True
        except razorpay.errors.SignatureVerificationError:
            return False

    def create_order(self, amount_paise: int) -> RazorpayOrder:
        try:
            order = self._client.order.create(
                {
                    "amount": amount_paise,
                    "currency": "INR",
                    "payment_capture": 1,
                }
            )
        except Exception as e:
            raise BillingProviderError(f"Failed to create Razorpay order: {e}")
        return RazorpayOrder(razorpay_order_id=order["id"])

    def verify_payment_signature(self, order_id: str, payment_id: str, signature: str) -> bool:
        try:
            self._client.utility.verify_payment_signature(
                {
                    "razorpay_order_id": order_id,
                    "razorpay_payment_id": payment_id,
                    "razorpay_signature": signature,
                }
            )
            return True
        except razorpay.errors.SignatureVerificationError:
            return False

    def parse_webhook(self, payload: dict) -> SubscriptionWebhookEvent:
        event = payload["event"]
        sub_entity = payload["payload"]["subscription"]["entity"]
        payment_entity = payload.get("payload", {}).get("payment", {}).get("entity")

        current_start = sub_entity.get("current_start")
        current_end = sub_entity.get("current_end")
        return SubscriptionWebhookEvent(
            event=event,
            razorpay_subscription_id=sub_entity["id"],
            razorpay_payment_id=payment_entity["id"] if payment_entity else None,
            amount_paise=payment_entity["amount"] if payment_entity else None,
            current_period_start=(
                datetime.utcfromtimestamp(current_start) if current_start else None
            ),
            current_period_end=(
                datetime.utcfromtimestamp(current_end) if current_end else None
            ),
        )
