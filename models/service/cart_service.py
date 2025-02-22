from models.entity.cart_entity import CartEntity
from models.entity.cart_item_entity import CartItemEntity

class CartService(object):
    def __init__(self, cart_entity: CartEntity):
        self.cart_entity = cart_entity

    def add_item(self, item: CartItemEntity):
        self.cart_entity.add_item(item)

    def remove_item(self, item: CartItemEntity):
        self.cart_entity.remove_item(item)

    def clear(self):
        self.cart_entity.clear()

    def get_total_price(self):
        return self.cart_entity.get_total_price()

    def get_total_quantity(self):
        return self.cart_entity.get_total_quantity()
