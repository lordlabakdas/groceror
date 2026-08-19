from datetime import datetime

import pytest

from engine.delivery.fake_provider import (
    FLAT_FEE,
    UNSERVICEABLE_LAT,
    UNSERVICEABLE_LNG,
    FakeDeliveryProvider,
)
from engine.delivery.provider import Coordinates, DeliveryUnavailableError


def test_get_quote_returns_flat_fee():
    provider = FakeDeliveryProvider()
    quote = provider.get_quote(
        Coordinates(12.9, 77.6), Coordinates(13.0, 80.2), weight_kg=5.0
    )
    assert quote.fee == FLAT_FEE
    assert quote.expires_at > datetime.utcnow()


def test_get_quote_raises_for_unserviceable_dropoff():
    provider = FakeDeliveryProvider()
    with pytest.raises(DeliveryUnavailableError):
        provider.get_quote(
            Coordinates(12.9, 77.6),
            Coordinates(UNSERVICEABLE_LAT, UNSERVICEABLE_LNG),
            weight_kg=5.0,
        )


def test_create_delivery_succeeds_for_fresh_quote():
    provider = FakeDeliveryProvider()
    quote = provider.get_quote(
        Coordinates(12.9, 77.6), Coordinates(13.0, 80.2), weight_kg=5.0
    )
    delivery = provider.create_delivery(quote.quote_id, order_ref="order-123")
    assert delivery.vendor_delivery_id
    assert delivery.status == "confirmed"


def test_create_delivery_raises_for_unknown_quote_id():
    provider = FakeDeliveryProvider()
    with pytest.raises(DeliveryUnavailableError):
        provider.create_delivery("not-a-real-quote-id", order_ref="order-123")


def test_get_status_and_cancel_roundtrip():
    provider = FakeDeliveryProvider()
    quote = provider.get_quote(
        Coordinates(12.9, 77.6), Coordinates(13.0, 80.2), weight_kg=5.0
    )
    delivery = provider.create_delivery(quote.quote_id, order_ref="order-123")

    status_update = provider.get_status(delivery.vendor_delivery_id)
    assert status_update.status == "confirmed"

    provider.cancel(delivery.vendor_delivery_id)
    with pytest.raises(DeliveryUnavailableError):
        provider.get_status(delivery.vendor_delivery_id)


def test_parse_webhook_extracts_fields():
    provider = FakeDeliveryProvider()
    update = provider.parse_webhook(
        {
            "vendor_delivery_id": "fake_delivery_abc",
            "status": "picked_up",
            "rider_name": "Ravi",
            "rider_phone": "+91-90000-00000",
            "tracking_url": "https://example.com/track/abc",
        }
    )
    assert update.status == "picked_up"
    assert update.rider_name == "Ravi"
