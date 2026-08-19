"""Vendor-agnostic delivery dispatch interface.

Every concrete courier integration (Shiprocket Quick today; anything else
later) implements ``DeliveryProvider`` so order/checkout code never talks to
a vendor's API shape directly. See SPEC_DELIVERY_DISPATCH.md §3.1.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Protocol


@dataclass
class Coordinates:
    lat: float
    lng: float


@dataclass
class Quote:
    quote_id: str
    fee: float
    expires_at: datetime
    serviceable: bool = True


@dataclass
class VendorDelivery:
    vendor_delivery_id: str
    status: str


@dataclass
class DeliveryStatusUpdate:
    vendor_delivery_id: str
    status: str
    rider_name: Optional[str] = None
    rider_phone: Optional[str] = None
    tracking_url: Optional[str] = None


class DeliveryUnavailableError(Exception):
    """Raised when a provider can't quote or dispatch (address out of
    coverage, quote expired, vendor rejected the request, etc.)."""


class DeliveryProvider(Protocol):
    def get_quote(
        self, pickup: Coordinates, dropoff: Coordinates, weight_kg: float
    ) -> Quote:
        """Raises DeliveryUnavailableError if the dropoff isn't serviceable."""
        ...

    def create_delivery(self, quote_id: str, order_ref: str) -> VendorDelivery:
        """Raises DeliveryUnavailableError if the quote is stale/rejected."""
        ...

    def get_status(self, vendor_delivery_id: str) -> DeliveryStatusUpdate: ...

    def cancel(self, vendor_delivery_id: str) -> None: ...

    def parse_webhook(self, payload: dict) -> DeliveryStatusUpdate:
        """Turn an inbound webhook body into a status update. Signature
        verification happens separately, at the API layer, before this is
        called — see api/webhook_api.py."""
        ...
