import pytest
from unittest.mock import MagicMock, patch
from uuid import uuid4


def _make_inventory(inv_id, store_id, price=2.50):
    inv = MagicMock()
    inv.id = inv_id
    inv.store_id = store_id
    inv.price = price
    return inv


def test_create_order_snapshots_prices():
    from api.validators.order_validation import CreateOrderRequest, OrderLineItem
    from models.entity.order_item_entity import OrderItem
    from models.service.orders_service import OrderService

    store_id = uuid4()
    inv_id = uuid4()
    fake_inv = _make_inventory(inv_id, store_id, price=3.00)

    with patch("models.service.orders_service.db_session") as mock_db:
        mock_db.exec.return_value.all.return_value = [fake_inv]
        user = MagicMock()
        user.id = uuid4()

        req = CreateOrderRequest(items=[OrderLineItem(inventory_id=inv_id, quantity=2)])
        OrderService().create_order(req, user)

        # One Order add + one OrderItem add
        assert mock_db.add.call_count == 2
        mock_db.commit.assert_called_once()

        calls = mock_db.add.call_args_list
        order_items = [c[0][0] for c in calls if isinstance(c[0][0], OrderItem)]
        assert len(order_items) == 1
        assert order_items[0].price == 3.00
        assert order_items[0].quantity == 2


def test_create_order_computes_total_price():
    from api.validators.order_validation import CreateOrderRequest, OrderLineItem
    from models.entity.orders_entity import Order as OrderEntity
    from models.service.orders_service import OrderService

    store_id = uuid4()
    inv_id = uuid4()
    fake_inv = _make_inventory(inv_id, store_id, price=2.50)

    with patch("models.service.orders_service.db_session") as mock_db:
        mock_db.exec.return_value.all.return_value = [fake_inv]
        user = MagicMock()
        user.id = uuid4()

        req = CreateOrderRequest(items=[OrderLineItem(inventory_id=inv_id, quantity=4)])
        OrderService().create_order(req, user)

        calls = mock_db.add.call_args_list
        order_entities = [c[0][0] for c in calls if isinstance(c[0][0], OrderEntity)]
        assert len(order_entities) == 1
        assert order_entities[0].total_price == 10.00  # 4 * 2.50


def test_create_order_raises_if_inventory_missing():
    from api.validators.order_validation import CreateOrderRequest, OrderLineItem
    from models.service.orders_service import OrderService

    with patch("models.service.orders_service.db_session") as mock_db:
        mock_db.exec.return_value.all.return_value = []  # inventory not found
        user = MagicMock()
        user.id = uuid4()
        req = CreateOrderRequest(items=[OrderLineItem(inventory_id=uuid4(), quantity=1)])

        with pytest.raises(ValueError, match="not found"):
            OrderService().create_order(req, user)


def test_create_order_raises_if_mixed_stores():
    from api.validators.order_validation import CreateOrderRequest, OrderLineItem
    from models.service.orders_service import OrderService

    inv1_id, inv2_id = uuid4(), uuid4()
    inv1 = _make_inventory(inv1_id, uuid4(), price=1.0)
    inv2 = _make_inventory(inv2_id, uuid4(), price=2.0)  # different store_id

    with patch("models.service.orders_service.db_session") as mock_db:
        mock_db.exec.return_value.all.return_value = [inv1, inv2]
        user = MagicMock()
        user.id = uuid4()
        req = CreateOrderRequest(items=[
            OrderLineItem(inventory_id=inv1_id, quantity=1),
            OrderLineItem(inventory_id=inv2_id, quantity=1),
        ])

        with pytest.raises(ValueError, match="same store"):
            OrderService().create_order(req, user)
