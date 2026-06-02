import pytest
from uuid import uuid4


def test_order_line_item_valid():
    from api.validators.order_validation import OrderLineItem
    item = OrderLineItem(inventory_id=uuid4(), quantity=2)
    assert item.quantity == 2


def test_order_line_item_default_quantity():
    from api.validators.order_validation import OrderLineItem
    item = OrderLineItem(inventory_id=uuid4())
    assert item.quantity == 1


def test_create_order_request_rejects_empty_items():
    from api.validators.order_validation import CreateOrderRequest
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        CreateOrderRequest(items=[])


def test_create_order_request_valid():
    from api.validators.order_validation import CreateOrderRequest, OrderLineItem
    req = CreateOrderRequest(items=[OrderLineItem(inventory_id=uuid4(), quantity=3)])
    assert len(req.items) == 1
    assert req.order_date is not None


def test_order_history_line_item():
    from api.validators.order_validation import OrderHistoryLineItem
    item = OrderHistoryLineItem(inventory_id=uuid4(), name="Apples", quantity=2, price=1.50)
    assert item.name == "Apples"
    assert item.price == 1.50


def test_store_order_line_item():
    from api.validators.order_validation import StoreOrderLineItem
    item = StoreOrderLineItem(inventory_id=uuid4(), name="Milk", quantity=1, price=2.00)
    assert item.name == "Milk"
