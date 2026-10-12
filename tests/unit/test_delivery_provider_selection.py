"""Tests for get_delivery_provider()'s real-vendor-vs-stub selection.

Mirrors send_sms()'s Twilio-credentials-or-stdout fallback
(api/helpers/auth_helper.py): no SHIPROCKET_API_KEY configured means the
app runs against an in-memory stub instead of crashing or silently no-op'ing.
"""
from unittest.mock import patch

from config import ShiprocketConfig
from engine.delivery import get_delivery_provider
from engine.delivery.fake_provider import FakeDeliveryProvider
from engine.delivery.shiprocket_quick import ShiprocketQuickProvider


def test_returns_fake_provider_when_no_api_key():
    with patch.object(ShiprocketConfig, "API_KEY", ""):
        assert isinstance(get_delivery_provider(), FakeDeliveryProvider)


def test_returns_shiprocket_provider_when_api_key_set():
    with patch.object(ShiprocketConfig, "API_KEY", "a-real-key"):
        assert isinstance(get_delivery_provider(), ShiprocketQuickProvider)


def test_fake_provider_is_a_singleton_across_calls():
    """A quote made in one request has to survive to a later request's
    create_delivery() call — only true if both calls get the same instance,
    since FakeDeliveryProvider keeps state on self, not at module level."""
    with patch.object(ShiprocketConfig, "API_KEY", ""):
        first = get_delivery_provider()
        second = get_delivery_provider()
    assert first is second


def test_fake_provider_quote_survives_across_calls_end_to_end():
    with patch.object(ShiprocketConfig, "API_KEY", ""):
        from engine.delivery.provider import Coordinates

        provider = get_delivery_provider()
        quote = provider.get_quote(Coordinates(12.9, 77.6), Coordinates(13.0, 80.2), 5.0)

        # Simulate a later, separate request asking for the same provider.
        delivery = get_delivery_provider().create_delivery(quote.quote_id, order_ref="o-1")
        assert delivery.status == "confirmed"
