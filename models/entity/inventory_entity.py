from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel


class InventoryCategory(str, Enum):
    GROCERY = "GROCERY"
    PRODUCE = "PRODUCE"
    MEAT = "MEAT"
    DAIRY = "DAIRY"
    BAKERY = "BAKERY"
    OTHER = "OTHER"


class Inventory(SQLModel, table=True):
    id: Optional[UUID] = Field(default_factory=uuid4, primary_key=True)
    name: str = Field(index=True)
    quantity: int = Field(default=0)
    category: InventoryCategory
    user_id: UUID = Field(foreign_key="user.id")
    store_id: UUID = Field(foreign_key="store.id")
    price: float = Field(default=0.0)
    notes: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    # user: "User" = Relationship(back_populates="inventory")

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "quantity": self.quantity,
            "category": self.category,
            "user_id": self.user_id,
            "store_id": self.store_id,
            "price": self.price,
            "notes": self.notes,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
