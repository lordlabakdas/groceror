from models.entity.cart_item_entity import CartItemEntity


class CartItemService(object):
    def __init__(self, cart_item_entity: CartItemEntity):
        self.cart_item_entity = cart_item_entity

    def add_item(self, item: CartItemEntity):
        self.cart_item_entity.add_item(item)

    def remove_item(self, item: CartItemEntity):
        self.cart_item_entity.remove_item(item)

    def clear(self):
        self.cart_item_entity.clear()
