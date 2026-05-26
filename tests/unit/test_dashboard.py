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
