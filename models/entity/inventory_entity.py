import datetime
from enum import Enum
from typing import Optional
from uuid import UUID

from sqlmodel import Column, Field, SQLModel


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
    category: InventoryCategory
    user_id = Field(foreign_key="user.id")
    timestamp: datetime = Column(nullable=False, default=datetime.datetime.utcnow)
    notes: str
