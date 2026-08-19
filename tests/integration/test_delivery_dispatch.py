"""
Integration tests for delivery dispatch (SPEC_DELIVERY_DISPATCH.md).

Uses FakeDeliveryProvider throughout — constitution Principle II forbids
live vendor calls in the test suite, and ShiprocketQuickProvider is
explicitly unverified against real docs anyway (see engine/delivery/
shiprocket_quick.py).
"""

import uuid
from unittest.mock import patch

import pytest

from engine.delivery.fake_provider import (
    UNSERVICEABLE_LAT,
    UNSERVICEABLE_LNG,
    FakeDeliveryProvider,
)
from tests.integration.helpers import (
    _headers,
    _login,
    _otp_and_verify,
    _register,
    client,
)

_suffix = str(uuid.uuid4().int)[:6]


def _phone(n: str) -> str:
    return f"+1570{_suffix}{n}"


@pytest.fixture(scope="module")
def shopper_token():
    _otp_and_verify(_phone("1"))
    _register(_phone("1"), "user")
    token = _login(_phone("1"))
    r = client.post(
        "/user/set-profile",
        json={
            "name": "Delivery Test Shopper",
            "email": "deliveryshopper@groceror.test",
        },
        headers=_headers(token),
    )
    assert r.status_code == 200, r.text
    return token


@pytest.fixture(scope="module")
def store_token():
    _otp_and_verify(_phone("2"))
    _register(_phone("2"), "store")
    return _login(_phone("2"))


@pytest.fixture(scope="module")
def store_id(store_token):
    r = client.post(
        "/stores/",
        json={
            "name": "Delivery Test Store",
            "email": "deliverytest@groceror.test",
            "website": "https://deliverytest.groceror.test",
            "location": "1 Test Street",
        },
        headers=_headers(store_token),
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


@pytest.fixture(scope="module")
def delivery_zone(store_token, store_id):
    r = client.put(
        "/delivery-zones",
        json={"latitude": 12.9716, "longitude": 77.5946, "radius_km": 10},
        headers=_headers(store_token),
    )
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture(scope="module")
def inventory_id(store_token, store_id, delivery_zone):
    r = client.post(
        "/inventory/add-inventory",
        json={"name": "Bananas", "quantity": 50, "category": "PRODUCE", "price": 2.0},
        headers=_headers(store_token),
    )
    assert r.status_code == 200, r.text
    return r.json()["inventory_id"]


class TestDeliveryQuote:
    def test_quote_returns_fee(self, shopper_token, store_id, inventory_id):
        with patch(
            "models.service.delivery_service.get_delivery_provider",
            return_value=FakeDeliveryProvider(),
        ):
            r = client.post(
                "/order/delivery-quote",
                json={"store_id": store_id, "dropoff_lat": 13.0, "dropoff_lng": 80.2},
                headers=_headers(shopper_token),
            )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["fee"] == 45.0
        assert "quote_id" in body

    def test_quote_fails_for_unserviceable_address(
        self, shopper_token, store_id, inventory_id
    ):
        with patch(
            "models.service.delivery_service.get_delivery_provider",
            return_value=FakeDeliveryProvider(),
        ):
            r = client.post(
                "/order/delivery-quote",
                json={
                    "store_id": store_id,
                    "dropoff_lat": UNSERVICEABLE_LAT,
                    "dropoff_lng": UNSERVICEABLE_LNG,
                },
                headers=_headers(shopper_token),
            )
        assert r.status_code == 400
        assert "not serviceable" in r.json()["detail"]

    def test_quote_requires_auth(self, store_id):
        r = client.post(
            "/order/delivery-quote",
            json={"store_id": store_id, "dropoff_lat": 13.0, "dropoff_lng": 80.2},
        )
        assert r.status_code in (401, 403)


class TestOrderCreationWithDelivery:
    def test_create_order_with_delivery_charges_fee(self, shopper_token, inventory_id):
        with patch(
            "models.service.delivery_service.get_delivery_provider",
            return_value=FakeDeliveryProvider(),
        ):
            r = client.post(
                "/order/create-order",
                json={
                    "items": [{"inventory_id": inventory_id, "quantity": 2}],
                    "delivery_address_line": "12 Anna Salai",
                    "delivery_lat": 13.0,
                    "delivery_lng": 80.2,
                },
                headers=_headers(shopper_token),
            )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["delivery_fee"] == 45.0
        assert body["total_price"] == pytest.approx(2 * 2.0 + 45.0)

    def test_create_order_without_delivery_has_no_fee(
        self, shopper_token, inventory_id
    ):
        r = client.post(
            "/order/create-order",
            json={"items": [{"inventory_id": inventory_id, "quantity": 1}]},
            headers=_headers(shopper_token),
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["delivery_fee"] is None
        assert body["total_price"] == pytest.approx(2.0)


class TestRequestDelivery:
    @pytest.fixture()
    def ready_order_id(self, shopper_token, store_token, inventory_id):
        """A fresh order per test, created with a delivery address and
        advanced to 'ready' so request-delivery is legal."""
        with patch(
            "models.service.delivery_service.get_delivery_provider",
            return_value=FakeDeliveryProvider(),
        ):
            r = client.post(
                "/order/create-order",
                json={
                    "items": [{"inventory_id": inventory_id, "quantity": 1}],
                    "delivery_address_line": "12 Anna Salai",
                    "delivery_lat": 13.0,
                    "delivery_lng": 80.2,
                },
                headers=_headers(shopper_token),
            )
        assert r.status_code == 200, r.text
        order_id = r.json()["id"]

        r = client.put(
            f"/order/{order_id}/status",
            json={"status": "ready"},
            headers=_headers(store_token),
        )
        assert r.status_code == 200, r.text
        return order_id

    def test_request_delivery_success(self, store_token, ready_order_id):
        with patch(
            "models.service.delivery_service.get_delivery_provider",
            return_value=FakeDeliveryProvider(),
        ):
            r = client.post(
                f"/order/{ready_order_id}/request-delivery",
                headers=_headers(store_token),
            )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "confirmed"
        assert body["quoted_fee"] == 45.0

    def test_request_delivery_twice_rejected(self, store_token, ready_order_id):
        provider = FakeDeliveryProvider()
        with patch(
            "models.service.delivery_service.get_delivery_provider",
            return_value=provider,
        ):
            first = client.post(
                f"/order/{ready_order_id}/request-delivery",
                headers=_headers(store_token),
            )
            assert first.status_code == 200, first.text

            second = client.post(
                f"/order/{ready_order_id}/request-delivery",
                headers=_headers(store_token),
            )
        assert second.status_code == 400
        assert "already" in second.json()["detail"]

    def test_request_delivery_requires_store_role(self, shopper_token, ready_order_id):
        r = client.post(
            f"/order/{ready_order_id}/request-delivery",
            headers=_headers(shopper_token),
        )
        assert r.status_code == 403

    def test_store_orders_list_reflects_delivery_status(
        self, store_token, shopper_token, ready_order_id
    ):
        with patch(
            "models.service.delivery_service.get_delivery_provider",
            return_value=FakeDeliveryProvider(),
        ):
            r = client.post(
                f"/order/{ready_order_id}/request-delivery",
                headers=_headers(store_token),
            )
        assert r.status_code == 200, r.text

        store_orders = client.get(
            "/order/store-orders", headers=_headers(store_token)
        ).json()
        row = next(o for o in store_orders["orders"] if o["id"] == ready_order_id)
        assert row["delivery_fee"] == 45.0
        assert row["delivery_status"] == "confirmed"

        history = client.get("/order/history", headers=_headers(shopper_token)).json()
        hrow = next(o for o in history["orders"] if o["id"] == ready_order_id)
        assert hrow["delivery_fee"] == 45.0
        assert hrow["delivery_status"] == "confirmed"


class TestShiprocketWebhook:
    def test_webhook_rejects_unsigned_request(self):
        r = client.post(
            "/webhooks/shiprocket-quick",
            json={"vendor_delivery_id": "fake_delivery_x", "status": "picked_up"},
        )
        assert r.status_code == 401
