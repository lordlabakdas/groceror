from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID

from sqlmodel import Field, SQLModel


class InventoryCategory(Enum):
    PRODUCE = "produce"
    MEAT_AND_POULTRY = "meat_and_poultry"
    DAIRY_AND_EGGS = "dairy_and_eggs"
    FROZEN_FOOD = "frozen_foods"
    CANNED_FOOD = "canned_food"


class Inventory(SQLModel, table=True):
    id: Optional[UUID] = Field(default=None, primary_key=True)
    name: str
    quantity: int
    category: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    notes: Optional[str] = None
    user_id: int = Field(foreign_key="user.id")
    # user: User = Relationship("User", back_populates="inventories")
