from unittest.mock import patch
from uuid import uuid4


def test_tier_for_spend_zero_is_bronze():
    from models.service.orders_service import _tier_for_spend

    assert _tier_for_spend(0.0) == ("bronze", 1.0)


def test_tier_for_spend_just_below_silver_is_bronze():
    from models.service.orders_service import _tier_for_spend

    assert _tier_for_spend(249.99) == ("bronze", 1.0)


def test_tier_for_spend_at_silver_threshold():
    from models.service.orders_service import _tier_for_spend

    assert _tier_for_spend(250.0) == ("silver", 1.25)


def test_tier_for_spend_just_below_gold_is_silver():
    from models.service.orders_service import _tier_for_spend

    assert _tier_for_spend(749.99) == ("silver", 1.25)


def test_tier_for_spend_at_gold_threshold():
    from models.service.orders_service import _tier_for_spend

    assert _tier_for_spend(750.0) == ("gold", 1.5)


def test_tier_for_spend_well_above_gold_stays_gold():
    from models.service.orders_service import _tier_for_spend

    assert _tier_for_spend(10_000.0) == ("gold", 1.5)


def test_get_lifetime_spend_returns_zero_when_no_orders():
    from models.service.orders_service import _get_lifetime_spend

    with patch("models.service.orders_service.db_session") as mock_db:
        mock_db.exec.return_value.first.return_value = None
        assert _get_lifetime_spend(uuid4()) == 0.0


def test_get_lifetime_spend_returns_summed_total():
    from models.service.orders_service import _get_lifetime_spend

    with patch("models.service.orders_service.db_session") as mock_db:
        mock_db.exec.return_value.first.return_value = 312.50
        assert _get_lifetime_spend(uuid4()) == 312.50


def test_get_tier_combines_spend_lookup_and_threshold():
    from models.service.orders_service import _get_tier

    with patch("models.service.orders_service._get_lifetime_spend", return_value=800.0):
        assert _get_tier(uuid4()) == ("gold", 1.5)
