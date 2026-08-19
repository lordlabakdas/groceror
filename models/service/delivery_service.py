# models/service/delivery_service.py
"""Delivery dispatch business logic. See SPEC_DELIVERY_DISPATCH.md.

Quotes are never persisted or trusted across a request boundary — every
consumer (checkout preview, order creation, dispatch request) asks the
active DeliveryProvider fresh. This is a deliberate v1 simplification: with
pass-through pricing (no Groceror markup), there's nothing a locked-in quote
protects that a cheap re-quote doesn't already handle, and it avoids an
entire class of quote-expiry edge cases. See SPEC_DELIVERY_DISPATCH.md §3.3.
"""

import logging
from datetime import datetime
from uuid import UUID

from sqlmodel import select

from engine.delivery import (
    Coordinates,
    DeliveryUnavailableError,
    Quote,
    get_delivery_provider,
)
from models.db import db_session
from models.entity.delivery_entity import Delivery
from models.entity.delivery_zone_entity import DeliveryZone
from models.entity.orders_entity import Order as OrderEntity

logger = logging.getLogger(__name__)

# Groceror doesn't track per-item weight anywhere; Shiprocket Quick's quote
# API wants one. A flat per-order estimate is a deliberate v1 simplification
# — revisit if real pricing turns out to be weight-sensitive enough to matter.
DEFAULT_ORDER_WEIGHT_KG = 5.0


class DeliveryService:
    def _pickup_point(self, store_id: UUID) -> Coordinates:
        zone = db_session.exec(
            select(DeliveryZone).where(DeliveryZone.store_id == store_id)
        ).first()
        if not zone:
            raise ValueError("Store has not configured a delivery zone")
        return Coordinates(lat=zone.latitude, lng=zone.longitude)

    def get_quote(
        self, store_id: UUID, dropoff_lat: float, dropoff_lng: float
    ) -> Quote:
        """Raises ValueError if the store has no delivery zone configured or
        the dropoff isn't serviceable."""
        pickup = self._pickup_point(store_id)
        dropoff = Coordinates(lat=dropoff_lat, lng=dropoff_lng)
        try:
            return get_delivery_provider().get_quote(
                pickup, dropoff, DEFAULT_ORDER_WEIGHT_KG
            )
        except DeliveryUnavailableError as e:
            raise ValueError(str(e))

    def request_delivery(self, order_id: UUID, store_id: UUID) -> Delivery:
        """Store-triggered dispatch. Re-quotes fresh (packing takes real
        time, so any earlier quote is stale) and books with the vendor.
        Raises ValueError for a not-found order or one with no delivery
        address on it (pickup order). On vendor failure, persists a
        `failed` Delivery row and returns it rather than raising — the
        caller (api/order_api.py) surfaces this as a clear message, no
        automatic retry, per SPEC_DELIVERY_DISPATCH.md §3.4.
        """
        order = db_session.exec(
            select(OrderEntity).where(
                OrderEntity.id == order_id, OrderEntity.store_id == store_id
            )
        ).first()
        if not order:
            raise ValueError("Order not found")
        if order.delivery_lat is None or order.delivery_lng is None:
            raise ValueError("Order has no delivery address — this is a pickup order")

        existing = db_session.exec(
            select(Delivery).where(Delivery.order_id == order_id)
        ).first()
        if existing and existing.status not in ("failed", "cancelled"):
            raise ValueError(f"Delivery already {existing.status} for this order")

        provider = get_delivery_provider()
        pickup = self._pickup_point(store_id)
        dropoff = Coordinates(lat=order.delivery_lat, lng=order.delivery_lng)

        delivery = existing or Delivery(
            order_id=order_id, store_id=store_id, quoted_fee=0.0
        )

        try:
            quote = provider.get_quote(pickup, dropoff, DEFAULT_ORDER_WEIGHT_KG)
            vendor_delivery = provider.create_delivery(
                quote.quote_id, order_ref=str(order_id)
            )
        except DeliveryUnavailableError as e:
            logger.warning("order_id=%s delivery request failed: %s", order_id, e)
            delivery.status = "failed"
            db_session.add(delivery)
            db_session.commit()
            db_session.refresh(delivery)
            return delivery

        delivery.vendor_quote_id = quote.quote_id
        delivery.vendor_delivery_id = vendor_delivery.vendor_delivery_id
        delivery.quoted_fee = quote.fee
        delivery.status = vendor_delivery.status
        delivery.requested_at = datetime.utcnow()
        delivery.updated_at = datetime.utcnow()
        db_session.add(delivery)
        db_session.commit()
        db_session.refresh(delivery)
        return delivery

    def get_delivery_for_order(self, order_id: UUID) -> Delivery | None:
        return db_session.exec(
            select(Delivery).where(Delivery.order_id == order_id)
        ).first()

    def get_delivery_by_vendor_id(self, vendor_delivery_id: str) -> Delivery | None:
        return db_session.exec(
            select(Delivery).where(Delivery.vendor_delivery_id == vendor_delivery_id)
        ).first()

    def apply_webhook_update(
        self,
        vendor_delivery_id: str,
        status: str,
        rider_name: str | None,
        rider_phone: str | None,
        tracking_url: str | None,
        raw_payload: str,
    ) -> Delivery | None:
        """Returns the updated Delivery, or None if no matching row was found
        (caller logs and no-ops rather than erroring — an update for an
        unknown delivery is not actionable)."""
        delivery = self.get_delivery_by_vendor_id(vendor_delivery_id)
        if not delivery:
            return None

        delivery.status = status
        if rider_name:
            delivery.rider_name = rider_name
        if rider_phone:
            delivery.rider_phone = rider_phone
        if tracking_url:
            delivery.tracking_url = tracking_url
        delivery.raw_webhook_payload = raw_payload
        delivery.updated_at = datetime.utcnow()
        if status == "delivered":
            delivery.delivered_at = datetime.utcnow()
        db_session.add(delivery)

        if status == "delivered":
            order = db_session.exec(
                select(OrderEntity).where(OrderEntity.id == delivery.order_id)
            ).first()
            if order:
                order.status = "delivered"
                db_session.add(order)

        db_session.commit()
        db_session.refresh(delivery)
        return delivery
