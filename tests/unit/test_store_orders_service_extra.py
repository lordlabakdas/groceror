"""
Extra unit-test coverage for models/service/orders_service.py and
models/service/store_service.py.

Follows the direct-unit-test / mocked-db_session pattern established in
tests/unit/test_order_service.py: patch("models.service.<module>.db_session")
and drive the service methods directly, without going through the FastAPI
app or a real HTTP client.
"""
from unittest.mock import MagicMock, patch
from uuid import uuid4
from datetime import date

import pytest
from fastapi import HTTPException


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_inventory(inv_id, store_id, price=2.50, quantity=100, name="Test Item"):
    inv = MagicMock()
    inv.id = inv_id
    inv.store_id = store_id
    inv.price = price
    inv.quantity = quantity
    inv.name = name
    return inv


def _all(items):
    """A fake `db_session.exec(...)` result whose `.all()` returns *items*."""
    m = MagicMock()
    m.all.return_value = items
    return m


def _first(item):
    """A fake `db_session.exec(...)` result whose `.first()` returns *item*."""
    m = MagicMock()
    m.first.return_value = item
    return m


def _make_coupon(**overrides):
    from models.entity.coupon_entity import Coupon

    fields = dict(
        code="SAVE10",
        discount_type="percent",
        discount_value=10.0,
        min_order_amount=None,
        max_uses=None,
        uses_count=0,
        store_id=None,
        valid_from=None,
        valid_until=None,
        is_active=True,
    )
    fields.update(overrides)
    return Coupon(**fields)


def _make_loyalty_account(**overrides):
    from models.entity.loyalty_account_entity import LoyaltyAccount

    fields = dict(user_id=uuid4(), points_balance=100, total_earned=0, total_redeemed=0)
    fields.update(overrides)
    return LoyaltyAccount(**fields)


# ─────────────────────────────────────────────────────────────────────────────
# OrderService.create_order — coupon handling (lines 80-104)
# ─────────────────────────────────────────────────────────────────────────────

def test_create_order_coupon_not_found_raises():
    from api.validators.order_validation import CreateOrderRequest, OrderLineItem
    from models.service.orders_service import OrderService

    store_id, inv_id = uuid4(), uuid4()
    fake_inv = _make_inventory(inv_id, store_id)

    with patch("models.service.orders_service.db_session") as mock_db:
        mock_db.exec.side_effect = [_all([fake_inv]), _first(None)]
        user = MagicMock(id=uuid4())
        req = CreateOrderRequest(
            items=[OrderLineItem(inventory_id=inv_id, quantity=2)],
            coupon_code="BADCODE",
        )
        with pytest.raises(ValueError, match="is not valid"):
            OrderService().create_order(req, user)


def test_create_order_coupon_inactive_raises():
    from api.validators.order_validation import CreateOrderRequest, OrderLineItem
    from models.service.orders_service import OrderService

    store_id, inv_id = uuid4(), uuid4()
    fake_inv = _make_inventory(inv_id, store_id)
    coupon = _make_coupon(is_active=False)

    with patch("models.service.orders_service.db_session") as mock_db:
        mock_db.exec.side_effect = [_all([fake_inv]), _first(coupon)]
        user = MagicMock(id=uuid4())
        req = CreateOrderRequest(
            items=[OrderLineItem(inventory_id=inv_id, quantity=2)],
            coupon_code="save10",
        )
        with pytest.raises(ValueError, match="is not valid"):
            OrderService().create_order(req, user)


def test_create_order_coupon_not_yet_active_raises():
    from api.validators.order_validation import CreateOrderRequest, OrderLineItem
    from models.service.orders_service import OrderService

    store_id, inv_id = uuid4(), uuid4()
    fake_inv = _make_inventory(inv_id, store_id)
    coupon = _make_coupon(valid_from=date(2999, 1, 1))

    with patch("models.service.orders_service.db_session") as mock_db:
        mock_db.exec.side_effect = [_all([fake_inv]), _first(coupon)]
        user = MagicMock(id=uuid4())
        req = CreateOrderRequest(
            items=[OrderLineItem(inventory_id=inv_id, quantity=2)],
            coupon_code="SAVE10",
        )
        with pytest.raises(ValueError, match="not yet active"):
            OrderService().create_order(req, user)


def test_create_order_coupon_expired_raises():
    from api.validators.order_validation import CreateOrderRequest, OrderLineItem
    from models.service.orders_service import OrderService

    store_id, inv_id = uuid4(), uuid4()
    fake_inv = _make_inventory(inv_id, store_id)
    coupon = _make_coupon(valid_until=date(2000, 1, 1))

    with patch("models.service.orders_service.db_session") as mock_db:
        mock_db.exec.side_effect = [_all([fake_inv]), _first(coupon)]
        user = MagicMock(id=uuid4())
        req = CreateOrderRequest(
            items=[OrderLineItem(inventory_id=inv_id, quantity=2)],
            coupon_code="SAVE10",
        )
        with pytest.raises(ValueError, match="has expired"):
            OrderService().create_order(req, user)


def test_create_order_coupon_usage_limit_reached_raises():
    from api.validators.order_validation import CreateOrderRequest, OrderLineItem
    from models.service.orders_service import OrderService

    store_id, inv_id = uuid4(), uuid4()
    fake_inv = _make_inventory(inv_id, store_id)
    coupon = _make_coupon(max_uses=5, uses_count=5)

    with patch("models.service.orders_service.db_session") as mock_db:
        mock_db.exec.side_effect = [_all([fake_inv]), _first(coupon)]
        user = MagicMock(id=uuid4())
        req = CreateOrderRequest(
            items=[OrderLineItem(inventory_id=inv_id, quantity=2)],
            coupon_code="SAVE10",
        )
        with pytest.raises(ValueError, match="usage limit"):
            OrderService().create_order(req, user)


def test_create_order_coupon_min_order_amount_not_met_raises():
    from api.validators.order_validation import CreateOrderRequest, OrderLineItem
    from models.service.orders_service import OrderService

    store_id, inv_id = uuid4(), uuid4()
    fake_inv = _make_inventory(inv_id, store_id, price=2.50)
    coupon = _make_coupon(min_order_amount=100.0)

    with patch("models.service.orders_service.db_session") as mock_db:
        mock_db.exec.side_effect = [_all([fake_inv]), _first(coupon)]
        user = MagicMock(id=uuid4())
        req = CreateOrderRequest(
            items=[OrderLineItem(inventory_id=inv_id, quantity=2)],  # subtotal 5.00
            coupon_code="SAVE10",
        )
        with pytest.raises(ValueError, match="minimum order"):
            OrderService().create_order(req, user)


def test_create_order_coupon_wrong_store_raises():
    from api.validators.order_validation import CreateOrderRequest, OrderLineItem
    from models.service.orders_service import OrderService

    store_id, inv_id = uuid4(), uuid4()
    fake_inv = _make_inventory(inv_id, store_id, price=2.50)
    coupon = _make_coupon(store_id=uuid4())  # different store

    with patch("models.service.orders_service.db_session") as mock_db:
        mock_db.exec.side_effect = [_all([fake_inv]), _first(coupon)]
        user = MagicMock(id=uuid4())
        req = CreateOrderRequest(
            items=[OrderLineItem(inventory_id=inv_id, quantity=2)],
            coupon_code="SAVE10",
        )
        with pytest.raises(ValueError, match="not valid for this store"):
            OrderService().create_order(req, user)


def test_create_order_coupon_percent_discount_applied():
    from api.validators.order_validation import CreateOrderRequest, OrderLineItem
    from models.service.orders_service import OrderService

    store_id, inv_id = uuid4(), uuid4()
    fake_inv = _make_inventory(inv_id, store_id, price=2.50)
    coupon = _make_coupon(discount_type="percent", discount_value=10.0)
    acct = _make_loyalty_account(points_balance=0)

    with patch("models.service.orders_service.db_session") as mock_db:
        # coupon lookup, tier lifetime-spend lookup (no prior spend), then the
        # unconditional loyalty-account lookup inside the try block.
        mock_db.exec.side_effect = [_all([fake_inv]), _first(coupon), _first(None), _first(acct)]
        user = MagicMock(id=uuid4())
        req = CreateOrderRequest(
            items=[OrderLineItem(inventory_id=inv_id, quantity=2)],  # subtotal 5.00
            coupon_code="save10",
        )
        order_entity, points_earned = OrderService().create_order(req, user)

        assert order_entity.coupon_code == "SAVE10"
        assert order_entity.discount_amount == 0.50
        assert order_entity.total_price == 4.50
        assert coupon.uses_count == 1
        assert points_earned == 4
        mock_db.commit.assert_called_once()


def test_create_order_coupon_fixed_discount_applied():
    from api.validators.order_validation import CreateOrderRequest, OrderLineItem
    from models.service.orders_service import OrderService

    store_id, inv_id = uuid4(), uuid4()
    fake_inv = _make_inventory(inv_id, store_id, price=2.50)
    coupon = _make_coupon(discount_type="fixed", discount_value=1.00)
    acct = _make_loyalty_account(points_balance=0)

    with patch("models.service.orders_service.db_session") as mock_db:
        mock_db.exec.side_effect = [_all([fake_inv]), _first(coupon), _first(None), _first(acct)]
        user = MagicMock(id=uuid4())
        req = CreateOrderRequest(
            items=[OrderLineItem(inventory_id=inv_id, quantity=2)],  # subtotal 5.00
            coupon_code="SAVE10",
        )
        order_entity, points_earned = OrderService().create_order(req, user)

        assert order_entity.discount_amount == 1.00
        assert order_entity.total_price == 4.00
        assert coupon.uses_count == 1
        assert points_earned == 4
        mock_db.commit.assert_called_once()


# ─────────────────────────────────────────────────────────────────────────────
# OrderService.create_order — loyalty points redemption (lines 110-116, 154-156)
# ─────────────────────────────────────────────────────────────────────────────

def test_create_order_insufficient_points_raises():
    from api.validators.order_validation import CreateOrderRequest, OrderLineItem
    from models.service.orders_service import OrderService

    store_id, inv_id = uuid4(), uuid4()
    fake_inv = _make_inventory(inv_id, store_id, price=2.50)
    acct = _make_loyalty_account(points_balance=10)

    with patch("models.service.orders_service.db_session") as mock_db:
        mock_db.exec.side_effect = [_all([fake_inv]), _first(acct)]
        user = MagicMock(id=uuid4())
        req = CreateOrderRequest(
            items=[OrderLineItem(inventory_id=inv_id, quantity=1)],
            points_to_redeem=500,
        )
        with pytest.raises(ValueError, match="Insufficient loyalty points"):
            OrderService().create_order(req, user)


def test_create_order_redeems_points_and_awards_new_points():
    from api.validators.order_validation import CreateOrderRequest, OrderLineItem
    from models.service.orders_service import OrderService

    store_id, inv_id = uuid4(), uuid4()
    fake_inv = _make_inventory(inv_id, store_id, price=2.50)
    acct = _make_loyalty_account(points_balance=100, total_earned=0, total_redeemed=0)

    with patch("models.service.orders_service.db_session") as mock_db:
        # validation lookup, tier lifetime-spend lookup (no prior spend), then
        # the unconditional lookup inside the try block — first and third
        # resolve to the same loyalty account object.
        mock_db.exec.side_effect = [_all([fake_inv]), _first(acct), _first(None), _first(acct)]
        user = MagicMock(id=uuid4())
        req = CreateOrderRequest(
            items=[OrderLineItem(inventory_id=inv_id, quantity=4)],  # subtotal 10.00
            points_to_redeem=50,
        )
        order_entity, points_earned = OrderService().create_order(req, user)

        assert order_entity.points_redeemed == 50
        assert order_entity.discount_amount == 0.50
        assert order_entity.total_price == 9.50
        assert points_earned == 9
        assert acct.points_balance == 59  # 100 - 50 + 9
        assert acct.total_redeemed == 50
        assert acct.total_earned == 9
        mock_db.commit.assert_called_once()


# ─────────────────────────────────────────────────────────────────────────────
# OrderService.create_order — exception / rollback path (lines 182-185)
# ─────────────────────────────────────────────────────────────────────────────

def test_create_order_rolls_back_and_reraises_on_db_error():
    from api.validators.order_validation import CreateOrderRequest, OrderLineItem
    from models.service.orders_service import OrderService

    store_id, inv_id = uuid4(), uuid4()
    fake_inv = _make_inventory(inv_id, store_id, price=2.50)

    with patch("models.service.orders_service.db_session") as mock_db:
        mock_db.exec.side_effect = [_all([fake_inv]), _first(None), _first(None)]
        mock_db.commit.side_effect = Exception("db exploded")
        user = MagicMock(id=uuid4())
        req = CreateOrderRequest(items=[OrderLineItem(inventory_id=inv_id, quantity=1)])

        with pytest.raises(Exception, match="db exploded"):
            OrderService().create_order(req, user)

        mock_db.rollback.assert_called_once()


# ─────────────────────────────────────────────────────────────────────────────
# OrderService — simple read/update methods (lines 187-217)
# ─────────────────────────────────────────────────────────────────────────────

def test_get_order_by_id_returns_order():
    from models.service.orders_service import OrderService

    fake_order = MagicMock()
    with patch("models.service.orders_service.db_session") as mock_db:
        mock_db.exec.return_value.first.return_value = fake_order
        result = OrderService().get_order_by_id(uuid4())
        assert result is fake_order


def test_get_orders_by_user_returns_list():
    from models.service.orders_service import OrderService

    fake_orders = [MagicMock(), MagicMock()]
    with patch("models.service.orders_service.db_session") as mock_db:
        mock_db.exec.return_value.all.return_value = fake_orders
        result = OrderService().get_orders_by_user(uuid4())
        assert result == fake_orders


def test_get_orders_by_store_returns_list():
    from models.service.orders_service import OrderService

    fake_orders = [MagicMock()]
    with patch("models.service.orders_service.db_session") as mock_db:
        mock_db.exec.return_value.all.return_value = fake_orders
        result = OrderService().get_orders_by_store(uuid4())
        assert result == fake_orders


def test_update_order_status_not_found_returns_none():
    from models.service.orders_service import OrderService

    with patch("models.service.orders_service.db_session") as mock_db:
        mock_db.exec.return_value.first.return_value = None
        result = OrderService().update_order_status(uuid4(), uuid4(), "confirmed")
        assert result is None
        mock_db.commit.assert_not_called()


def test_update_order_status_updates_and_commits():
    from models.service.orders_service import OrderService

    fake_order = MagicMock()
    with patch("models.service.orders_service.db_session") as mock_db:
        mock_db.exec.return_value.first.return_value = fake_order
        result = OrderService().update_order_status(uuid4(), uuid4(), "confirmed")
        assert result is fake_order
        assert fake_order.status == "confirmed"
        mock_db.commit.assert_called_once()
        mock_db.refresh.assert_called_once_with(fake_order)


# ─────────────────────────────────────────────────────────────────────────────
# StoreService — exception branches and simple lookups
# ─────────────────────────────────────────────────────────────────────────────

def test_store_service_create_store_success():
    from models.service.store_service import StoreService

    with patch("models.service.store_service.db_session") as mock_db:
        store = StoreService().create_store(
            name="Test Store", entity_id=uuid4(), email="t@example.com",
            website="https://x.test", location="Somewhere",
        )
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()
        mock_db.refresh.assert_called_once()
        assert store.name == "Test Store"
        assert store.email == "t@example.com"


def test_store_service_create_store_db_error_raises_400():
    from models.service.store_service import StoreService

    with patch("models.service.store_service.db_session") as mock_db:
        mock_db.commit.side_effect = Exception("db exploded")
        with pytest.raises(HTTPException) as exc_info:
            StoreService().create_store(name="Test", entity_id=uuid4(), email="t@example.com")
        assert exc_info.value.status_code == 400
        assert "Failed to create store" in exc_info.value.detail
        mock_db.rollback.assert_called_once()


def test_store_service_get_store_by_email_found():
    from models.service.store_service import StoreService

    fake_store = MagicMock()
    with patch("models.service.store_service.db_session") as mock_db:
        mock_db.exec.return_value.first.return_value = fake_store
        assert StoreService().get_store_by_email("a@b.com") is fake_store


def test_store_service_get_store_by_email_not_found():
    from models.service.store_service import StoreService

    with patch("models.service.store_service.db_session") as mock_db:
        mock_db.exec.return_value.first.return_value = None
        assert StoreService().get_store_by_email("nope@b.com") is None


def test_store_service_update_store_not_found_reraises_404():
    from models.service.store_service import StoreService

    with patch("models.service.store_service.db_session") as mock_db:
        mock_db.exec.return_value.first.return_value = None
        with pytest.raises(HTTPException) as exc_info:
            StoreService().update_store(uuid4(), name="New Name")
        assert exc_info.value.status_code == 404


def test_store_service_update_store_db_error_raises_400():
    from models.service.store_service import StoreService

    fake_store = MagicMock()
    with patch("models.service.store_service.db_session") as mock_db:
        mock_db.exec.return_value.first.return_value = fake_store
        mock_db.commit.side_effect = Exception("boom")
        with pytest.raises(HTTPException) as exc_info:
            StoreService().update_store(uuid4(), name="New Name")
        assert exc_info.value.status_code == 400
        assert "Failed to update store" in exc_info.value.detail
        mock_db.rollback.assert_called_once()


def test_store_service_delete_store_not_found_reraises_404():
    from models.service.store_service import StoreService

    with patch("models.service.store_service.db_session") as mock_db:
        mock_db.exec.return_value.first.return_value = None
        with pytest.raises(HTTPException) as exc_info:
            StoreService().delete_store(uuid4())
        assert exc_info.value.status_code == 404


def test_store_service_delete_store_db_error_raises_400():
    from models.service.store_service import StoreService

    fake_store = MagicMock()
    with patch("models.service.store_service.db_session") as mock_db:
        mock_db.exec.return_value.first.return_value = fake_store
        mock_db.commit.side_effect = Exception("boom")
        with pytest.raises(HTTPException) as exc_info:
            StoreService().delete_store(uuid4())
        assert exc_info.value.status_code == 400
        assert "Failed to delete store" in exc_info.value.detail
        mock_db.rollback.assert_called_once()


def test_store_service_get_all_active_stores():
    from models.service.store_service import StoreService

    fake_stores = [MagicMock(), MagicMock()]
    with patch("models.service.store_service.db_session") as mock_db:
        mock_db.exec.return_value.all.return_value = fake_stores
        assert StoreService().get_all_active_stores() == fake_stores


def test_store_service_get_store_owner_found():
    from models.service.store_service import StoreService

    fake_store = MagicMock(entity_id=uuid4())
    fake_owner = MagicMock()
    with patch("models.service.store_service.db_session") as mock_db:
        mock_db.exec.return_value.first.side_effect = [fake_store, fake_owner]
        result = StoreService().get_store_owner(uuid4())
        assert result is fake_owner


def test_store_service_get_store_owner_not_found_raises_404():
    from models.service.store_service import StoreService

    fake_store = MagicMock(entity_id=uuid4())
    with patch("models.service.store_service.db_session") as mock_db:
        mock_db.exec.return_value.first.side_effect = [fake_store, None]
        with pytest.raises(HTTPException) as exc_info:
            StoreService().get_store_owner(uuid4())
        assert exc_info.value.status_code == 404


def test_store_service_get_store_email():
    from models.service.store_service import StoreService

    fake_store = MagicMock(email="store@example.com")
    with patch("models.service.store_service.db_session") as mock_db:
        mock_db.exec.return_value.first.return_value = fake_store
        assert StoreService().get_store_email(uuid4()) == "store@example.com"
