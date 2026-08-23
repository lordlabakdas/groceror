"""In-memory BillingProvider for tests — no live network calls.

Per constitution Principle II (test isolation), nothing in the test suite
should hit Razorpay's real API. This fake gives deterministic, configurable
responses instead, mirroring engine/delivery/fake_provider.py's shape.
"""

from datetime import datetime, timedelta
from uuid import uuid4

from engine.billing.provider import (
    RazorpayCustomer,
    RazorpayOrder,
    RazorpaySubscription,
    SubscriptionWebhookEvent,
)

VALID_SIGNATURE = "fake-valid-signature"
VALID_PAYMENT_SIGNATURE = "fake-valid-payment-signature"


class FakeBillingProvider:
    def __init__(self):
        self.plans: dict[str, int] = {}
        self.customers: dict[str, dict] = {}
        self.subscriptions: dict[str, dict] = {}
        self.cancelled: set[str] = set()
        self.orders: dict[str, int] = {}

    def create_plan(self, price_paise: int) -> str:
        plan_id = f"fake_plan_{uuid4().hex[:8]}"
        self.plans[plan_id] = price_paise
        return plan_id

    def create_customer(self, name: str, email: str, contact: str) -> RazorpayCustomer:
        customer_id = f"fake_cust_{uuid4().hex[:8]}"
        self.customers[customer_id] = {"name": name, "email": email, "contact": contact}
        return RazorpayCustomer(razorpay_customer_id=customer_id)

    def create_subscription(self, plan_id, customer_id, start_at) -> RazorpaySubscription:
        subscription_id = f"fake_sub_{uuid4().hex[:8]}"
        self.subscriptions[subscription_id] = {
            "plan_id": plan_id,
            "customer_id": customer_id,
            "start_at": start_at,
        }
        return RazorpaySubscription(razorpay_subscription_id=subscription_id)

    def cancel_subscription(self, subscription_id: str) -> None:
        self.cancelled.add(subscription_id)

    def verify_webhook_signature(self, raw_body: bytes, signature: str | None) -> bool:
        return signature == VALID_SIGNATURE

    def create_order(self, amount_paise: int) -> RazorpayOrder:
        order_id = f"fake_order_{uuid4().hex[:8]}"
        self.orders[order_id] = amount_paise
        return RazorpayOrder(razorpay_order_id=order_id)

    def verify_payment_signature(self, order_id: str, payment_id: str, signature: str) -> bool:
        return signature == VALID_PAYMENT_SIGNATURE

    def parse_webhook(self, payload: dict) -> SubscriptionWebhookEvent:
        event = payload["event"]
        sub_entity = payload["payload"]["subscription"]["entity"]
        payment_entity = payload.get("payload", {}).get("payment", {}).get("entity")
        now = datetime.utcnow()
        return SubscriptionWebhookEvent(
            event=event,
            razorpay_subscription_id=sub_entity["id"],
            razorpay_payment_id=payment_entity["id"] if payment_entity else None,
            amount_paise=payment_entity["amount"] if payment_entity else None,
            current_period_start=sub_entity.get("current_start_dt", now),
            current_period_end=sub_entity.get("current_end_dt", now + timedelta(days=30)),
        )
