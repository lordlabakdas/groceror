class CartService(object):
    def __init__(self, cart_repository: CartRepository):
        self.cart_repository = cart_repository

    def add_item(self, item: CartItemEntity):
        self.cart_repository.add_item(item)
