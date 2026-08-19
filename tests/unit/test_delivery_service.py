from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from engine.delivery.provider import DeliveryUnavailableError, Quote, VendorDelivery


def _make_zone(store_id, lat=12.97, lng=77.59):
    zone = MagicMock()
    zone.store_id = store_id
    zone.latitude = lat
    zone.longitude = lng
    return zone


def test_get_quote_returns_provider_quote():
    from models.service.delivery_service import DeliveryService

    store_id = uuid4()
    fake_quote = Quote(quote_id="q1", fee=45.0, expires_at=MagicMock())

    with patch("models.service.delivery_service.db_session") as mock_db, patch(
        "models.service.delivery_service.get_delivery_provider"
    ) as mock_get_provider:
        mock_db.exec.return_value.first.return_value = _make_zone(store_id)
        mock_provider = MagicMock()
        mock_provider.get_quote.return_value = fake_quote
        mock_get_provider.return_value = mock_provider

        quote = DeliveryService().get_quote(
            store_id, dropoff_lat=13.0, dropoff_lng=80.2
        )

        assert quote is fake_quote
        mock_provider.get_quote.assert_called_once()


def test_get_quote_raises_if_store_has_no_delivery_zone():
    from models.service.delivery_service import DeliveryService

    with patch("models.service.delivery_service.db_session") as mock_db:
        mock_db.exec.return_value.first.return_value = None

        with pytest.raises(ValueError, match="delivery zone"):
            DeliveryService().get_quote(uuid4(), dropoff_lat=13.0, dropoff_lng=80.2)


def test_get_quote_wraps_provider_unavailable_error():
    from models.service.delivery_service import DeliveryService

    store_id = uuid4()
    with patch("models.service.delivery_service.db_session") as mock_db, patch(
        "models.service.delivery_service.get_delivery_provider"
    ) as mock_get_provider:
        mock_db.exec.return_value.first.return_value = _make_zone(store_id)
        mock_provider = MagicMock()
        mock_provider.get_quote.side_effect = DeliveryUnavailableError(
            "not serviceable"
        )
        mock_get_provider.return_value = mock_provider

        with pytest.raises(ValueError, match="not serviceable"):
            DeliveryService().get_quote(store_id, dropoff_lat=0.0, dropoff_lng=0.0)


def test_request_delivery_raises_if_order_not_found():
    from models.service.delivery_service import DeliveryService

    with patch("models.service.delivery_service.db_session") as mock_db:
        mock_db.exec.return_value.first.return_value = None

        with pytest.raises(ValueError, match="not found"):
            DeliveryService().request_delivery(uuid4(), uuid4())


def test_request_delivery_raises_for_pickup_order():
    from models.service.delivery_service import DeliveryService

    order = MagicMock()
    order.delivery_lat = None
    order.delivery_lng = None

    with patch("models.service.delivery_service.db_session") as mock_db:
        mock_db.exec.return_value.first.return_value = order

        with pytest.raises(ValueError, match="pickup"):
            DeliveryService().request_delivery(uuid4(), uuid4())


def test_request_delivery_success_books_with_provider():
    from models.entity.delivery_entity import Delivery
    from models.service.delivery_service import DeliveryService

    order = MagicMock()
    order.delivery_lat = 13.0
    order.delivery_lng = 80.2

    fake_quote = Quote(quote_id="q1", fee=45.0, expires_at=MagicMock())
    fake_vendor_delivery = VendorDelivery(vendor_delivery_id="vd_1", status="confirmed")

    call_results = iter(
        [order, None, _make_zone(uuid4())]
    )  # order lookup, existing-delivery lookup, zone lookup

    with patch("models.service.delivery_service.db_session") as mock_db, patch(
        "models.service.delivery_service.get_delivery_provider"
    ) as mock_get_provider:
        mock_db.exec.return_value.first.side_effect = call_results
        mock_provider = MagicMock()
        mock_provider.get_quote.return_value = fake_quote
        mock_provider.create_delivery.return_value = fake_vendor_delivery
        mock_get_provider.return_value = mock_provider

        delivery = DeliveryService().request_delivery(uuid4(), uuid4())

        assert isinstance(delivery, Delivery)
        assert delivery.status == "confirmed"
        assert delivery.vendor_delivery_id == "vd_1"
        assert delivery.quoted_fee == 45.0
        mock_db.commit.assert_called_once()


def test_request_delivery_marks_failed_on_provider_error():
    from models.service.delivery_service import DeliveryService

    order = MagicMock()
    order.delivery_lat = 13.0
    order.delivery_lng = 80.2

    call_results = iter([order, None, _make_zone(uuid4())])

    with patch("models.service.delivery_service.db_session") as mock_db, patch(
        "models.service.delivery_service.get_delivery_provider"
    ) as mock_get_provider:
        mock_db.exec.return_value.first.side_effect = call_results
        mock_provider = MagicMock()
        mock_provider.get_quote.side_effect = DeliveryUnavailableError("vendor down")
        mock_get_provider.return_value = mock_provider

        delivery = DeliveryService().request_delivery(uuid4(), uuid4())

        assert delivery.status == "failed"
        mock_db.commit.assert_called_once()


def test_request_delivery_raises_if_already_dispatched():
    from models.service.delivery_service import DeliveryService

    order = MagicMock()
    order.delivery_lat = 13.0
    order.delivery_lng = 80.2

    existing = MagicMock()
    existing.status = "in_transit"

    with patch("models.service.delivery_service.db_session") as mock_db:
        mock_db.exec.return_value.first.side_effect = iter([order, existing])

        with pytest.raises(ValueError, match="already in_transit"):
            DeliveryService().request_delivery(uuid4(), uuid4())


def test_apply_webhook_update_returns_none_for_unknown_delivery():
    from models.service.delivery_service import DeliveryService

    with patch("models.service.delivery_service.db_session") as mock_db:
        mock_db.exec.return_value.first.return_value = None

        result = DeliveryService().apply_webhook_update(
            "unknown_id", "picked_up", None, None, None, raw_payload="{}"
        )
        assert result is None


def test_apply_webhook_update_marks_order_delivered():
    from models.service.delivery_service import DeliveryService

    delivery = MagicMock()
    delivery.order_id = uuid4()
    order = MagicMock()

    with patch("models.service.delivery_service.db_session") as mock_db:
        mock_db.exec.return_value.first.side_effect = iter([delivery, order])

        result = DeliveryService().apply_webhook_update(
            "vd_1",
            "delivered",
            "Ravi",
            "+91-90000-00000",
            "https://track/1",
            raw_payload="{}",
        )

        assert result is delivery
        assert delivery.status == "delivered"
        assert delivery.rider_name == "Ravi"
        assert order.status == "delivered"
