"""Unit tests for ShiprocketQuickProvider's error-handling contract.

This vendor integration is unverified (see its module docstring) — these
tests don't assert anything about real Shiprocket Quick behavior. They only
assert the contract every DeliveryProvider caller relies on: whatever goes
wrong talking to the vendor (network failure, unexpected HTTP status,
malformed body), it must come back as DeliveryUnavailableError, never a raw
`requests` exception that would crash the request. A production incident
(delivery-quote 503ing instead of failing soft) is what prompted this file.
"""
from unittest.mock import MagicMock, patch

import pytest
import requests

from engine.delivery.provider import Coordinates, DeliveryUnavailableError
from engine.delivery.shiprocket_quick import ShiprocketQuickProvider


def _response(status_code=200, json_body=None, text=""):
    resp = MagicMock(spec=requests.Response)
    resp.status_code = status_code
    resp.text = text
    resp.json.return_value = json_body if json_body is not None else {}
    if status_code >= 400:
        resp.raise_for_status.side_effect = requests.exceptions.HTTPError(
            f"{status_code} error", response=resp
        )
    else:
        resp.raise_for_status.return_value = None
    return resp


# ─────────────────────────────────────────────────────────────────────────────
# get_quote
# ─────────────────────────────────────────────────────────────────────────────

def test_get_quote_connection_error_raises_delivery_unavailable():
    provider = ShiprocketQuickProvider()
    with patch.object(
        provider._session, "request", side_effect=requests.exceptions.ConnectionError()
    ):
        with pytest.raises(DeliveryUnavailableError):
            provider.get_quote(Coordinates(12.9, 77.6), Coordinates(13.0, 80.2), 5.0)


def test_get_quote_timeout_raises_delivery_unavailable():
    provider = ShiprocketQuickProvider()
    with patch.object(
        provider._session, "request", side_effect=requests.exceptions.Timeout()
    ):
        with pytest.raises(DeliveryUnavailableError):
            provider.get_quote(Coordinates(12.9, 77.6), Coordinates(13.0, 80.2), 5.0)


def test_get_quote_422_raises_unserviceable_message():
    provider = ShiprocketQuickProvider()
    with patch.object(provider._session, "request", return_value=_response(422)):
        with pytest.raises(DeliveryUnavailableError, match="not serviceable"):
            provider.get_quote(Coordinates(12.9, 77.6), Coordinates(13.0, 80.2), 5.0)


def test_get_quote_unexpected_5xx_raises_delivery_unavailable():
    provider = ShiprocketQuickProvider()
    with patch.object(provider._session, "request", return_value=_response(503)):
        with pytest.raises(DeliveryUnavailableError):
            provider.get_quote(Coordinates(12.9, 77.6), Coordinates(13.0, 80.2), 5.0)


def test_get_quote_malformed_json_raises_delivery_unavailable():
    provider = ShiprocketQuickProvider()
    resp = _response(200)
    resp.json.side_effect = ValueError("not json")
    with patch.object(provider._session, "request", return_value=resp):
        with pytest.raises(DeliveryUnavailableError):
            provider.get_quote(Coordinates(12.9, 77.6), Coordinates(13.0, 80.2), 5.0)


def test_get_quote_missing_field_raises_delivery_unavailable():
    provider = ShiprocketQuickProvider()
    resp = _response(200, json_body={"fee": 45.0})  # no quote_id/expires_at
    with patch.object(provider._session, "request", return_value=resp):
        with pytest.raises(DeliveryUnavailableError):
            provider.get_quote(Coordinates(12.9, 77.6), Coordinates(13.0, 80.2), 5.0)


def test_get_quote_success_returns_quote():
    provider = ShiprocketQuickProvider()
    resp = _response(
        200,
        json_body={
            "quote_id": "q_1",
            "fee": 45.0,
            "expires_at": "2026-01-01T00:00:00",
        },
    )
    with patch.object(provider._session, "request", return_value=resp):
        quote = provider.get_quote(Coordinates(12.9, 77.6), Coordinates(13.0, 80.2), 5.0)
    assert quote.quote_id == "q_1"
    assert quote.fee == 45.0


# ─────────────────────────────────────────────────────────────────────────────
# create_delivery
# ─────────────────────────────────────────────────────────────────────────────

def test_create_delivery_connection_error_raises_delivery_unavailable():
    provider = ShiprocketQuickProvider()
    with patch.object(
        provider._session, "request", side_effect=requests.exceptions.ConnectionError()
    ):
        with pytest.raises(DeliveryUnavailableError):
            provider.create_delivery("q_1", order_ref="order-123")


def test_create_delivery_409_raises_delivery_unavailable():
    provider = ShiprocketQuickProvider()
    with patch.object(provider._session, "request", return_value=_response(409)):
        with pytest.raises(DeliveryUnavailableError):
            provider.create_delivery("q_1", order_ref="order-123")


def test_create_delivery_success_returns_vendor_delivery():
    provider = ShiprocketQuickProvider()
    resp = _response(200, json_body={"delivery_id": "d_1", "status": "requested"})
    with patch.object(provider._session, "request", return_value=resp):
        delivery = provider.create_delivery("q_1", order_ref="order-123")
    assert delivery.vendor_delivery_id == "d_1"
    assert delivery.status == "requested"


# ─────────────────────────────────────────────────────────────────────────────
# get_status / cancel
# ─────────────────────────────────────────────────────────────────────────────

def test_get_status_timeout_raises_delivery_unavailable():
    provider = ShiprocketQuickProvider()
    with patch.object(
        provider._session, "request", side_effect=requests.exceptions.Timeout()
    ):
        with pytest.raises(DeliveryUnavailableError):
            provider.get_status("d_1")


def test_cancel_404_is_a_no_op():
    provider = ShiprocketQuickProvider()
    with patch.object(provider._session, "request", return_value=_response(404)):
        provider.cancel("d_1")  # must not raise


def test_cancel_unexpected_error_raises_delivery_unavailable():
    provider = ShiprocketQuickProvider()
    with patch.object(provider._session, "request", return_value=_response(500)):
        with pytest.raises(DeliveryUnavailableError):
            provider.cancel("d_1")
