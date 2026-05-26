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
