"""Unit tests for saved_deal_service's pure status-computation helpers
(SPEC_SAVED_DEALS.md §3.2) — no DB involved, just entity field logic."""
from datetime import date, datetime, timedelta
from uuid import uuid4

from models.entity.coupon_entity import Coupon
from models.entity.flash_sale_entity import FlashSale
from models.entity.promotion_entity import Promotion
from models.service.saved_deal_service import (
    _compute_coupon,
    _compute_flash_sale,
    _compute_promotion,
)

TODAY = date.today()
NOW = datetime.utcnow()


def _coupon(**overrides) -> Coupon:
    defaults = dict(
        code="TEST10", discount_type="percent", discount_value=10,
        is_active=True, valid_from=None, valid_until=None,
        max_uses=None, uses_count=0,
    )
    defaults.update(overrides)
    return Coupon(**defaults)


def _promo(**overrides) -> Promotion:
    defaults = dict(
        inventory_id=uuid4(), sale_price=5.0,
        start_date=TODAY - timedelta(days=1), end_date=TODAY + timedelta(days=1),
    )
    defaults.update(overrides)
    return Promotion(**defaults)


def _flash_sale(**overrides) -> FlashSale:
    defaults = dict(
        inventory_id=uuid4(), store_id=uuid4(), sale_price=3.0,
        start_at=NOW - timedelta(hours=1), end_at=NOW + timedelta(hours=1),
        is_active=True,
    )
    defaults.update(overrides)
    return FlashSale(**defaults)


# ---------------------------------------------------------------------------
# Coupon
# ---------------------------------------------------------------------------

def test_coupon_active_with_no_date_bounds():
    stat, expires_at, code, sale_price = _compute_coupon(_coupon())
    assert stat == "active"
    assert expires_at is None
    assert code == "TEST10"
    assert sale_price is None


def test_coupon_upcoming():
    stat, *_ = _compute_coupon(_coupon(valid_from=TODAY + timedelta(days=3)))
    assert stat == "upcoming"


def test_coupon_expired_by_date():
    stat, *_ = _compute_coupon(_coupon(valid_until=TODAY - timedelta(days=1)))
    assert stat == "expired"


def test_coupon_expired_by_deactivation():
    stat, *_ = _compute_coupon(_coupon(is_active=False))
    assert stat == "expired"


def test_coupon_expired_by_max_uses():
    stat, *_ = _compute_coupon(_coupon(max_uses=5, uses_count=5))
    assert stat == "expired"


def test_coupon_active_under_max_uses():
    stat, *_ = _compute_coupon(_coupon(max_uses=5, uses_count=4))
    assert stat == "active"


def test_coupon_expires_at_reflects_valid_until():
    valid_until = TODAY + timedelta(days=10)
    _, expires_at, _, _ = _compute_coupon(_coupon(valid_until=valid_until))
    assert expires_at == datetime.combine(valid_until, datetime.min.time())


# ---------------------------------------------------------------------------
# Promotion
# ---------------------------------------------------------------------------

def test_promotion_active():
    stat, expires_at, code, sale_price = _compute_promotion(_promo())
    assert stat == "active"
    assert code is None
    assert sale_price == 5.0


def test_promotion_upcoming():
    stat, *_ = _compute_promotion(_promo(start_date=TODAY + timedelta(days=2), end_date=TODAY + timedelta(days=5)))
    assert stat == "upcoming"


def test_promotion_expired():
    stat, *_ = _compute_promotion(_promo(start_date=TODAY - timedelta(days=5), end_date=TODAY - timedelta(days=1)))
    assert stat == "expired"


# ---------------------------------------------------------------------------
# Flash sale
# ---------------------------------------------------------------------------

def test_flash_sale_active():
    stat, expires_at, code, sale_price = _compute_flash_sale(_flash_sale())
    assert stat == "active"
    assert sale_price == 3.0
    assert code is None


def test_flash_sale_upcoming():
    stat, *_ = _compute_flash_sale(_flash_sale(start_at=NOW + timedelta(hours=2), end_at=NOW + timedelta(hours=4)))
    assert stat == "upcoming"


def test_flash_sale_expired_by_time():
    stat, *_ = _compute_flash_sale(_flash_sale(start_at=NOW - timedelta(hours=3), end_at=NOW - timedelta(hours=1)))
    assert stat == "expired"


def test_flash_sale_expired_by_deactivation():
    stat, *_ = _compute_flash_sale(_flash_sale(is_active=False))
    assert stat == "expired"
