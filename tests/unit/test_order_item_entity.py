from uuid import uuid4


def test_order_item_fields():
    from models.entity.order_item_entity import OrderItem
    order_id = uuid4()
    inv_id = uuid4()
    oi = OrderItem(order_id=order_id, inventory_id=inv_id, quantity=3, price=1.99)
    assert oi.order_id == order_id
    assert oi.inventory_id == inv_id
    assert oi.quantity == 3
    assert oi.price == 1.99


def test_order_item_defaults():
    from models.entity.order_item_entity import OrderItem
    oi = OrderItem(order_id=uuid4(), inventory_id=uuid4(), price=0.0)
    assert oi.quantity == 1
    assert oi.id is not None
    assert oi.created_at is not None
