"""Delivery dispatch package. Import `get_delivery_provider` to get the
active DeliveryProvider — this is the one place that decides which vendor
is live, so tests can monkeypatch it to FakeDeliveryProvider instead of
reaching the network (constitution Principle II).
"""

from engine.delivery.provider import (
    Coordinates,  # noqa: F401
    DeliveryProvider,
    DeliveryStatusUpdate,  # noqa: F401
    DeliveryUnavailableError,  # noqa: F401
    Quote,  # noqa: F401
    VendorDelivery,  # noqa: F401
)
from engine.delivery.shiprocket_quick import ShiprocketQuickProvider


def get_delivery_provider() -> DeliveryProvider:
    return ShiprocketQuickProvider()
