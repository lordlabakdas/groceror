from datetime import datetime
from sqlmodel import SQLModel, Field, Relationship
from enum import Enum
from typing import Optional
from uuid import UUID

from models.entity.user_entity import User


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
    user_id: int = Field(foreign_key="user.id")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    notes: Optional[str] = None
    user: Optional["User"] = Relationship(back_populates="inventory")
