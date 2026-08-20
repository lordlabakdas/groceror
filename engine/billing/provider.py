"""Vendor-agnostic billing/subscription interface.

Razorpay is the only implementation for v1, but subscription_service talks
to this Protocol, not to Razorpay's SDK directly — mirrors
engine/delivery/provider.py's shape. See SPEC_SUBSCRIPTION.md §3.4.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Protocol


@dataclass
class RazorpayCustomer:
    razorpay_customer_id: str


@dataclass
class RazorpaySubscription:
    razorpay_subscription_id: str


@dataclass
class SubscriptionWebhookEvent:
    """Normalized shape of an inbound Razorpay subscription webhook.
    `event` is one of: subscription.authenticated, subscription.activated,
    subscription.charged, subscription.pending, subscription.halted,
    subscription.cancelled. Payment fields are only present on
    subscription.charged."""

    event: str
    razorpay_subscription_id: str
    razorpay_payment_id: Optional[str] = None
    amount_paise: Optional[int] = None
    current_period_start: Optional[datetime] = None
    current_period_end: Optional[datetime] = None


class BillingProviderError(Exception):
    """Raised when the provider rejects a request (invalid plan, customer,
    or subscription state)."""


class BillingProvider(Protocol):
    def create_plan(self, price_paise: int) -> str:
        """Returns a Razorpay plan_id for a new monthly plan at this price."""
        ...

    def create_customer(self, name: str, email: str, contact: str) -> RazorpayCustomer: ...

    def create_subscription(
        self, plan_id: str, customer_id: str, start_at: datetime
    ) -> RazorpaySubscription:
        """`start_at` delays the first charge (e.g. to the end of a trial)."""
        ...

    def cancel_subscription(self, subscription_id: str) -> None:
        """Cancels at the end of the current billing cycle."""
        ...

    def verify_webhook_signature(self, raw_body: bytes, signature: Optional[str]) -> bool: ...

    def parse_webhook(self, payload: dict) -> SubscriptionWebhookEvent:
        """Signature verification happens separately, at the API layer,
        before this is called — see api/subscription_api.py."""
        ...
