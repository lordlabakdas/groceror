from datetime import datetime
from typing import List, Optional
from uuid import UUID, uuid4

from sqlmodel import Field, Relationship, SQLModel

from models.entity.cart_item_entity import CartItemEntity


class CartEntity(SQLModel, table=True):
    id: Optional[UUID] = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="user.id")
    store_id: UUID = Field(foreign_key="store.id")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    total_price: float = Field(default=0.0)
    total_quantity: int = Field(default=0)
    notes: Optional[str] = None
    is_active: bool = Field(default=True)

    # Define the relationship properly
    items: List["CartItemEntity"] = Relationship(back_populates="cart")

    def add_item(self, item: "CartItemEntity"):
        self.items.append(item)
        self.total_price += item.price * item.quantity
        self.total_quantity += item.quantity
        self.updated_at = datetime.utcnow()

    def remove_item(self, item: "CartItemEntity"):
        self.items.remove(item)
        self.total_price -= item.price * item.quantity
        self.total_quantity -= item.quantity

    def clear(self):
        self.items = []
        self.total_price = 0.0
        self.total_quantity = 0

    def get_total_price(self):
        return sum(item.price * item.quantity for item in self.items)

    def get_total_quantity(self):
        return sum(item.quantity for item in self.items)

    def get_items(self):
        return self.items
