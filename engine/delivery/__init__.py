"""Delivery dispatch package. Import `get_delivery_provider` to get the
active DeliveryProvider — this is the one place that decides which vendor
is live, so tests can monkeypatch it to FakeDeliveryProvider instead of
reaching the network (constitution Principle II).
"""

from engine.delivery.fake_provider import FakeDeliveryProvider
from engine.delivery.provider import (
    Coordinates,  # noqa: F401
    DeliveryProvider,
    DeliveryStatusUpdate,  # noqa: F401
    DeliveryUnavailableError,  # noqa: F401
    Quote,  # noqa: F401
    VendorDelivery,  # noqa: F401
)
from engine.delivery.shiprocket_quick import ShiprocketQuickProvider

# FakeDeliveryProvider keeps its quotes/deliveries in memory on the instance,
# so it has to be the *same* instance across requests — a quote created in
# one request's get_quote() call has to still be there when a later
# request's create_delivery() looks it up. The app runs as a single
# `uvicorn main:app` process (see Dockerfile), so a module-level singleton
# is safe here; it would not be if this ever ran with multiple workers or
# horizontally-scaled machines sharing no memory.
_fake_provider = FakeDeliveryProvider()


def get_delivery_provider() -> DeliveryProvider:
    """Real Shiprocket Quick once SHIPROCKET_API_KEY is configured (`fly
    secrets set SHIPROCKET_API_KEY=...`, see fly.toml); falls back to an
    in-memory stub otherwise — same pattern as send_sms() falling back to
    stdout when Twilio isn't configured (api/helpers/auth_helper.py). The
    stub quotes a flat fee for any address and "delivers" instantly on
    request_delivery() with no real courier involved — it's for exercising
    the checkout/dispatch flow end-to-end before a real vendor account
    exists, not a substitute for one."""
    from config import ShiprocketConfig

    if not ShiprocketConfig.API_KEY:
        return _fake_provider
    return ShiprocketQuickProvider()
