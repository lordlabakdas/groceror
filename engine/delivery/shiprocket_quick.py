"""Shiprocket Quick DeliveryProvider implementation.

UNVERIFIED PROVIDER: the endpoint paths, auth header, and payload shapes
below are a best-effort guess at a typical REST courier API, not a
transcription of Shiprocket Quick's real documentation — vendor evaluation
(see GROCEROR_CONTEXT.md §10) found their technical docs gated behind a
business account, which this project doesn't have yet. Per
SPEC_DELIVERY_DISPATCH.md's Implementation Order, the first real
implementation task is confirming this against actual credentials and
adjusting whatever's wrong here. Business logic tests use FakeDeliveryProvider
instead (constitution Principle II) — this class itself is only unit-tested
for its error-handling contract (see tests/unit/test_shiprocket_quick_provider.py):
whatever this unverified integration does wrong, every failure mode must come
back as DeliveryUnavailableError, never a raw exception that crashes the
request.
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

    def _request(self, method: str, path: str, **kwargs) -> requests.Response:
        """Every vendor call goes through here so a network failure (DNS,
        connection refused, timeout) raises DeliveryUnavailableError instead
        of a raw `requests` exception — this provider's endpoint shapes are
        unverified (see module docstring), so any request to it can fail in
        ways none of the call sites below anticipate. Letting that propagate
        crashed the request outright (observed in production as a 503 on
        the checkout delivery-quote call); every caller already expects
        DeliveryUnavailableError and fails soft on it."""
        try:
            return self._session.request(
                method, f"{self._base_url}{path}", timeout=10, **kwargs
            )
        except requests.exceptions.RequestException as e:
            logger.warning("Shiprocket Quick request to %s failed: %s", path, e)
            raise DeliveryUnavailableError("Delivery vendor is unavailable") from e

    def _json_body(self, resp: requests.Response, path: str) -> dict:
        """raise_for_status() plus a malformed-body guard, both converted to
        DeliveryUnavailableError for the same reason as _request() above."""
        try:
            resp.raise_for_status()
            return resp.json()
        except (requests.exceptions.HTTPError, ValueError) as e:
            logger.warning("Shiprocket Quick response from %s was unusable: %s", path, e)
            raise DeliveryUnavailableError("Delivery vendor is unavailable") from e

    def get_quote(
        self, pickup: Coordinates, dropoff: Coordinates, weight_kg: float
    ) -> Quote:
        resp = self._request(
            "POST",
            "/quote",
            json={
                "pickup": {"lat": pickup.lat, "lng": pickup.lng},
                "dropoff": {"lat": dropoff.lat, "lng": dropoff.lng},
                "weight_kg": weight_kg,
            },
        )
        if resp.status_code == 422:
            raise DeliveryUnavailableError("Dropoff address is not serviceable")
        try:
            body = self._json_body(resp, "/quote")
            return Quote(
                quote_id=body["quote_id"],
                fee=float(body["fee"]),
                expires_at=datetime.fromisoformat(body["expires_at"]),
            )
        except KeyError as e:
            logger.warning("Shiprocket Quick quote response missing %s", e)
            raise DeliveryUnavailableError("Delivery vendor is unavailable") from e

    def create_delivery(self, quote_id: str, order_ref: str) -> VendorDelivery:
        resp = self._request(
            "POST",
            "/deliveries",
            json={"quote_id": quote_id, "order_ref": order_ref},
        )
        if resp.status_code in (404, 409, 422):
            raise DeliveryUnavailableError(
                f"Shiprocket Quick rejected delivery creation for quote {quote_id}: {resp.text}"
            )
        try:
            body = self._json_body(resp, "/deliveries")
            return VendorDelivery(
                vendor_delivery_id=body["delivery_id"], status=body["status"]
            )
        except KeyError as e:
            logger.warning("Shiprocket Quick create_delivery response missing %s", e)
            raise DeliveryUnavailableError("Delivery vendor is unavailable") from e

    def get_status(self, vendor_delivery_id: str) -> DeliveryStatusUpdate:
        resp = self._request("GET", f"/deliveries/{vendor_delivery_id}")
        try:
            body = self._json_body(resp, f"/deliveries/{vendor_delivery_id}")
            return DeliveryStatusUpdate(
                vendor_delivery_id=vendor_delivery_id,
                status=body["status"],
                rider_name=body.get("rider_name"),
                rider_phone=body.get("rider_phone"),
                tracking_url=body.get("tracking_url"),
            )
        except KeyError as e:
            logger.warning("Shiprocket Quick status response missing %s", e)
            raise DeliveryUnavailableError("Delivery vendor is unavailable") from e

    def cancel(self, vendor_delivery_id: str) -> None:
        resp = self._request("POST", f"/deliveries/{vendor_delivery_id}/cancel")
        if resp.status_code not in (200, 204, 404):
            try:
                resp.raise_for_status()
            except requests.exceptions.HTTPError as e:
                logger.warning("Shiprocket Quick cancel request failed: %s", e)
                raise DeliveryUnavailableError("Delivery vendor is unavailable") from e

    def parse_webhook(self, payload: dict) -> DeliveryStatusUpdate:
        return DeliveryStatusUpdate(
            vendor_delivery_id=payload["vendor_delivery_id"],
            status=payload["status"],
            rider_name=payload.get("rider_name"),
            rider_phone=payload.get("rider_phone"),
            tracking_url=payload.get("tracking_url"),
        )
