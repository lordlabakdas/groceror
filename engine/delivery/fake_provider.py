"""In-memory DeliveryProvider for tests — no live network calls.

Per constitution Principle II (test isolation), nothing in the test suite
should hit Shiprocket Quick's real API. This fake gives deterministic,
configurable responses instead.
"""

from datetime import datetime, timedelta
from uuid import uuid4

from engine.delivery.provider import (
    Coordinates,
    DeliveryStatusUpdate,
    DeliveryUnavailableError,
    Quote,
    VendorDelivery,
)

# A dropoff at exactly this point is treated as out of coverage, so tests
# can exercise the "unserviceable address" path deterministically.
UNSERVICEABLE_LAT = 0.0
UNSERVICEABLE_LNG = 0.0

FLAT_FEE = 45.0


class FakeDeliveryProvider:
    def __init__(self):
        self._quotes: dict[str, Quote] = {}
        self._deliveries: dict[str, VendorDelivery] = {}

    def get_quote(
        self, pickup: Coordinates, dropoff: Coordinates, weight_kg: float
    ) -> Quote:
        if dropoff.lat == UNSERVICEABLE_LAT and dropoff.lng == UNSERVICEABLE_LNG:
            raise DeliveryUnavailableError("Address not serviceable")
        quote = Quote(
            quote_id=f"fake_quote_{uuid4().hex[:8]}",
            fee=FLAT_FEE,
            expires_at=datetime.utcnow() + timedelta(minutes=10),
        )
        self._quotes[quote.quote_id] = quote
        return quote

    def create_delivery(self, quote_id: str, order_ref: str) -> VendorDelivery:
        quote = self._quotes.get(quote_id)
        if not quote or quote.expires_at < datetime.utcnow():
            raise DeliveryUnavailableError(f"Quote {quote_id} is invalid or expired")
        delivery = VendorDelivery(
            vendor_delivery_id=f"fake_delivery_{uuid4().hex[:8]}",
            status="confirmed",
        )
        self._deliveries[delivery.vendor_delivery_id] = delivery
        return delivery

    def get_status(self, vendor_delivery_id: str) -> DeliveryStatusUpdate:
        delivery = self._deliveries.get(vendor_delivery_id)
        if not delivery:
            raise DeliveryUnavailableError(f"Unknown delivery {vendor_delivery_id}")
        return DeliveryStatusUpdate(
            vendor_delivery_id=vendor_delivery_id, status=delivery.status
        )

    def cancel(self, vendor_delivery_id: str) -> None:
        self._deliveries.pop(vendor_delivery_id, None)

    def parse_webhook(self, payload: dict) -> DeliveryStatusUpdate:
        return DeliveryStatusUpdate(
            vendor_delivery_id=payload["vendor_delivery_id"],
            status=payload["status"],
            rider_name=payload.get("rider_name"),
            rider_phone=payload.get("rider_phone"),
            tracking_url=payload.get("tracking_url"),
        )
