"""Shiprocket Quick DeliveryProvider implementation.

UNVERIFIED PROVIDER: the endpoint paths, auth header, and payload shapes
below are a best-effort guess at a typical REST courier API, not a
transcription of Shiprocket Quick's real documentation — vendor evaluation
(see GROCEROR_CONTEXT.md §10) found their technical docs gated behind a
business account, which this project doesn't have yet. Per
SPEC_DELIVERY_DISPATCH.md's Implementation Order, the first real
implementation task is confirming this against actual credentials and
adjusting whatever's wrong here. Nothing in the test suite exercises this
class — tests use FakeDeliveryProvider instead (constitution Principle II).
"""

import logging
from datetime import datetime

import requests

from config import ShiprocketConfig
from engine.delivery.provider import (
    Coordinates,
    DeliveryStatusUpdate,
    DeliveryUnavailableError,
    Quote,
    VendorDelivery,
)

logger = logging.getLogger(__name__)


class ShiprocketQuickProvider:
    def __init__(self):
        self._base_url = ShiprocketConfig.BASE_URL
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"Bearer {ShiprocketConfig.API_KEY}",
                "Content-Type": "application/json",
            }
        )

    def get_quote(
        self, pickup: Coordinates, dropoff: Coordinates, weight_kg: float
    ) -> Quote:
        resp = self._session.post(
            f"{self._base_url}/quote",
            json={
                "pickup": {"lat": pickup.lat, "lng": pickup.lng},
                "dropoff": {"lat": dropoff.lat, "lng": dropoff.lng},
                "weight_kg": weight_kg,
            },
            timeout=10,
        )
        if resp.status_code == 422:
            raise DeliveryUnavailableError("Dropoff address is not serviceable")
        resp.raise_for_status()
        body = resp.json()
        return Quote(
            quote_id=body["quote_id"],
            fee=float(body["fee"]),
            expires_at=datetime.fromisoformat(body["expires_at"]),
        )

    def create_delivery(self, quote_id: str, order_ref: str) -> VendorDelivery:
        resp = self._session.post(
            f"{self._base_url}/deliveries",
            json={"quote_id": quote_id, "order_ref": order_ref},
            timeout=10,
        )
        if resp.status_code in (404, 409, 422):
            raise DeliveryUnavailableError(
                f"Shiprocket Quick rejected delivery creation for quote {quote_id}: {resp.text}"
            )
        resp.raise_for_status()
        body = resp.json()
        return VendorDelivery(
            vendor_delivery_id=body["delivery_id"], status=body["status"]
        )

    def get_status(self, vendor_delivery_id: str) -> DeliveryStatusUpdate:
        resp = self._session.get(
            f"{self._base_url}/deliveries/{vendor_delivery_id}", timeout=10
        )
        resp.raise_for_status()
        body = resp.json()
        return DeliveryStatusUpdate(
            vendor_delivery_id=vendor_delivery_id,
            status=body["status"],
            rider_name=body.get("rider_name"),
            rider_phone=body.get("rider_phone"),
            tracking_url=body.get("tracking_url"),
        )

    def cancel(self, vendor_delivery_id: str) -> None:
        resp = self._session.post(
            f"{self._base_url}/deliveries/{vendor_delivery_id}/cancel", timeout=10
        )
        if resp.status_code not in (200, 204, 404):
            resp.raise_for_status()

    def parse_webhook(self, payload: dict) -> DeliveryStatusUpdate:
        return DeliveryStatusUpdate(
            vendor_delivery_id=payload["vendor_delivery_id"],
            status=payload["status"],
            rider_name=payload.get("rider_name"),
            rider_phone=payload.get("rider_phone"),
            tracking_url=payload.get("tracking_url"),
        )
