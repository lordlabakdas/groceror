"""Unit tests for dashboard validators and pure computation helpers."""
from datetime import date
from uuid import uuid4

import pytest


# ---------------------------------------------------------------------------
# SetThresholdPayload
# ---------------------------------------------------------------------------

def test_set_threshold_valid():
    from api.validators.inventory_validation import SetThresholdPayload
    p = SetThresholdPayload(threshold=5)
    assert p.threshold == 5


def test_set_threshold_zero_allowed():
    from api.validators.inventory_validation import SetThresholdPayload
    p = SetThresholdPayload(threshold=0)
    assert p.threshold == 0


def test_set_threshold_negative_rejected():
    from api.validators.inventory_validation import SetThresholdPayload
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        SetThresholdPayload(threshold=-1)


# ---------------------------------------------------------------------------
# SetExpiryPayload
# ---------------------------------------------------------------------------

def test_set_expiry_valid():
    from api.validators.inventory_validation import SetExpiryPayload
    p = SetExpiryPayload(expiry_date=date(2026, 12, 31))
    assert p.expiry_date == date(2026, 12, 31)


# ---------------------------------------------------------------------------
# Dashboard response models
# ---------------------------------------------------------------------------

def test_dashboard_response_empty():
    from api.validators.inventory_validation import DashboardResponse, TodaysSummary
    r = DashboardResponse(
        low_stock=[],
        todays_summary=TodaysSummary(order_count=0, revenue=0.0, orders=[]),
        expiring_soon=[],
        top_sellers=[],
    )
    assert r.todays_summary.revenue == 0.0
    assert r.low_stock == []


def test_todays_order():
    from api.validators.inventory_validation import TodaysOrder
    from datetime import datetime
    order = TodaysOrder(
        id=uuid4(),
        total_price=24.50,
        status="pending",
        order_date=datetime(2026, 5, 26, 10, 0),
    )
    assert order.total_price == 24.50
    assert order.status == "pending"


def test_low_stock_item():
    from api.validators.inventory_validation import LowStockItem
    item = LowStockItem(id=uuid4(), name="Milk", quantity=2, threshold=5)
    assert item.quantity == 2
    assert item.threshold == 5
    assert item.name == "Milk"


def test_expiring_item():
    from api.validators.inventory_validation import ExpiringItem
    item = ExpiringItem(
        id=uuid4(), name="Yogurt", quantity=3,
        expiry_date=date(2026, 5, 28), days_remaining=2,
    )
    assert item.days_remaining == 2


def test_top_seller_item():
    from api.validators.inventory_validation import TopSellerItem
    item = TopSellerItem(id=uuid4(), name="Apples", units_sold=42, revenue=125.58)
    assert item.revenue == 125.58


# ---------------------------------------------------------------------------
# Threshold endpoint logic (mock db_session)
# ---------------------------------------------------------------------------

from unittest.mock import MagicMock, patch


def test_threshold_creates_new_row():
    """set_stock_threshold inserts a new StockThreshold when none exists."""
    inv_id = uuid4()
    store = MagicMock()
    store.id = uuid4()
    mock_item = MagicMock()
    mock_item.id = inv_id

    with patch("api.inventory_api.db_session") as mock_db, \
         patch("api.inventory_api.InventoryHelper") as MockHelper:
        mock_helper = MockHelper.return_value
        mock_helper._require_store.return_value = store

        exec_item = MagicMock()
        exec_item.first.return_value = mock_item
        exec_threshold = MagicMock()
        exec_threshold.first.return_value = None  # no existing threshold
        mock_db.exec.side_effect = [exec_item, exec_threshold]

        from api.validators.inventory_validation import SetThresholdPayload
        from api.inventory_api import set_stock_threshold

        import asyncio
        payload = SetThresholdPayload(threshold=10)

        async def run():
            return await set_stock_threshold(inv_id, payload, user=MagicMock())

        result = asyncio.run(run())
        assert result == {"status": "success"}
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()


def test_threshold_updates_existing_row():
    """set_stock_threshold updates threshold on an existing StockThreshold row."""
    inv_id = uuid4()
    store = MagicMock()
    store.id = uuid4()
    mock_item = MagicMock()
    mock_item.id = inv_id
    mock_existing = MagicMock()
    mock_existing.threshold = 5

    with patch("api.inventory_api.db_session") as mock_db, \
         patch("api.inventory_api.InventoryHelper") as MockHelper:
        mock_helper = MockHelper.return_value
        mock_helper._require_store.return_value = store

        exec_item = MagicMock()
        exec_item.first.return_value = mock_item
        exec_threshold = MagicMock()
        exec_threshold.first.return_value = mock_existing
        mock_db.exec.side_effect = [exec_item, exec_threshold]

        from api.validators.inventory_validation import SetThresholdPayload
        from api.inventory_api import set_stock_threshold

        import asyncio
        payload = SetThresholdPayload(threshold=20)

        async def run():
            return await set_stock_threshold(inv_id, payload, user=MagicMock())

        asyncio.run(run())
        assert mock_existing.threshold == 20
        mock_db.add.assert_not_called()
        mock_db.commit.assert_called_once()


def test_expiry_creates_new_row():
    """set_inventory_expiry inserts a new InventoryExpiry when none exists."""
    inv_id = uuid4()
    store = MagicMock()
    store.id = uuid4()
    mock_item = MagicMock()

    with patch("api.inventory_api.db_session") as mock_db, \
         patch("api.inventory_api.InventoryHelper") as MockHelper:
        mock_helper = MockHelper.return_value
        mock_helper._require_store.return_value = store

        exec_item = MagicMock()
        exec_item.first.return_value = mock_item
        exec_expiry = MagicMock()
        exec_expiry.first.return_value = None
        mock_db.exec.side_effect = [exec_item, exec_expiry]

        from api.validators.inventory_validation import SetExpiryPayload
        from api.inventory_api import set_inventory_expiry

        import asyncio
        payload = SetExpiryPayload(expiry_date=date(2026, 12, 31))

        async def run():
            return await set_inventory_expiry(inv_id, payload, user=MagicMock())

        result = asyncio.run(run())
        assert result == {"status": "success"}
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()


def test_expiry_updates_existing_row():
    """set_inventory_expiry updates expiry_date on an existing InventoryExpiry row."""
    inv_id = uuid4()
    store = MagicMock()
    store.id = uuid4()
    mock_item = MagicMock()
    mock_existing = MagicMock()
    mock_existing.expiry_date = date(2026, 6, 1)

    with patch("api.inventory_api.db_session") as mock_db, \
         patch("api.inventory_api.InventoryHelper") as MockHelper:
        mock_helper = MockHelper.return_value
        mock_helper._require_store.return_value = store

        exec_item = MagicMock()
        exec_item.first.return_value = mock_item
        exec_expiry = MagicMock()
        exec_expiry.first.return_value = mock_existing
        mock_db.exec.side_effect = [exec_item, exec_expiry]

        from api.validators.inventory_validation import SetExpiryPayload
        from api.inventory_api import set_inventory_expiry

        import asyncio
        payload = SetExpiryPayload(expiry_date=date(2026, 12, 31))

        async def run():
            return await set_inventory_expiry(inv_id, payload, user=MagicMock())

        asyncio.run(run())
        assert mock_existing.expiry_date == date(2026, 12, 31)
        mock_db.add.assert_not_called()
        mock_db.commit.assert_called_once()


# ---------------------------------------------------------------------------
# _compute_top_sellers pure function
# ---------------------------------------------------------------------------

def test_compute_top_sellers_counts_correctly():
    from api.dashboard_api import _compute_top_sellers

    id1 = uuid4()
    id2 = uuid4()

    class FakeOrder:
        def __init__(self, items):
            self.items = items

    orders = [
        FakeOrder([str(id1), str(id1), str(id2)]),
        FakeOrder([str(id1)]),
    ]

    class FakeItem:
        def __init__(self, uid, name, price):
            self.id = uid
            self.name = name
            self.price = price

    inventory_map = {
        id1: FakeItem(id1, "Apples", 3.00),
        id2: FakeItem(id2, "Milk", 2.50),
    }

    results = _compute_top_sellers(orders, inventory_map)
    assert results[0].name == "Apples"
    assert results[0].units_sold == 3
    assert results[0].revenue == 9.00
    assert results[1].name == "Milk"
    assert results[1].units_sold == 1


def test_compute_top_sellers_skips_invalid_uuid():
    from api.dashboard_api import _compute_top_sellers

    class FakeOrder:
        def __init__(self, items):
            self.items = items

    orders = [FakeOrder(["not-a-uuid", "also-bad"])]
    results = _compute_top_sellers(orders, {})
    assert results == []


def test_compute_top_sellers_skips_missing_inventory():
    from api.dashboard_api import _compute_top_sellers

    id1 = uuid4()

    class FakeOrder:
        def __init__(self, items):
            self.items = items

    orders = [FakeOrder([str(id1)])]
    # id1 not in inventory_map
    results = _compute_top_sellers(orders, {})
    assert results == []


# ---------------------------------------------------------------------------
# GET /dashboard/ - integration test via TestClient
# ---------------------------------------------------------------------------

def test_get_dashboard_returns_all_four_sections():
    """GET /dashboard/ returns the four widget sections when authenticated as store."""
    from unittest.mock import MagicMock, patch
    from fastapi.testclient import TestClient
    from main import app
    from helpers.jwt import auth_required

    mock_user = MagicMock()
    mock_store = MagicMock()
    mock_store.id = uuid4()

    async def override_auth():
        return mock_user

    app.dependency_overrides[auth_required] = override_auth

    try:
        with patch("api.dashboard_api.InventoryHelper") as MockHelper, \
             patch("api.dashboard_api.db_session") as mock_db:

            MockHelper.return_value._require_store.return_value = mock_store

            # All queries return empty results
            mock_exec = MagicMock()
            mock_exec.all.return_value = []
            mock_db.exec.return_value = mock_exec

            client = TestClient(app)
            response = client.get("/dashboard/")

            assert response.status_code == 200
            data = response.json()
            assert "low_stock" in data
            assert "todays_summary" in data
            assert "expiring_soon" in data
            assert "top_sellers" in data
            assert data["todays_summary"]["order_count"] == 0
            assert data["todays_summary"]["revenue"] == 0.0
    finally:
        app.dependency_overrides.pop(auth_required, None)
