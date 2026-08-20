"""Billing package. Import `get_billing_provider` to get the active
BillingProvider — this is the one place that decides which vendor is live,
so tests can monkeypatch it to FakeBillingProvider instead of reaching the
network (constitution Principle II). Mirrors engine/delivery/__init__.py.
"""

from engine.billing.provider import (
    BillingProvider,
    BillingProviderError,  # noqa: F401
    RazorpayCustomer,  # noqa: F401
    RazorpaySubscription,  # noqa: F401
    SubscriptionWebhookEvent,  # noqa: F401
)
from engine.billing.razorpay_provider import RazorpayProvider


def get_billing_provider() -> BillingProvider:
    return RazorpayProvider()
