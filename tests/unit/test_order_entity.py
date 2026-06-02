from uuid import uuid4


def test_order_has_no_items_column():
    from models.entity.orders_entity import Order
    assert not hasattr(Order, "items"), "Order.items ARRAY column should be removed"


def test_order_fields():
    from models.entity.orders_entity import Order
    o = Order(user_id=uuid4(), total_price=9.99, status="pending")
    assert o.status == "pending"
    assert o.total_price == 9.99
    assert o.order_id is not None
