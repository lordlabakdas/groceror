from models.entity.user_entity import User


class Cart(object):
    def __init__(self, user: User):
        self.user = user
        self.items = []

    def add_item(self, item: dict):
        self.items.append(item)

    def remove_item(self, item: dict):
        self.items.remove(item)

    def get_cart(self):
        return self.items

    def clear_cart(self):
        self.items = []

    def get_total(self):
        return sum(item["price"] for item in self.items)

    def checkout(self):
        self.clear_cart()
        return self.get_cart_total()

    def get_cart_items(self):
        return self.items

    def get_cart_total(self):
        return self.get_total()

    def get_cart_count(self):
        return len(self.items)

    def get_cart_items_total(self):
        return sum(item["price"] for item in self.items)
