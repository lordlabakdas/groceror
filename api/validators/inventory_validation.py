from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, validator

from models.entity.inventory_entity import InventoryCategory


class AddInventoryPayload(BaseModel):
    name: str
    quantity: int
    category: InventoryCategory
    notes: Optional[str] = None

    @validator("category")
    def check_category(cls, v):
        if not isinstance(v, InventoryCategory):
            raise ValueError(
                f"invalid category value: must be part of {list(InventoryCategory.__members__.values())}"
            )
        return v


class AddInventoryResponse(BaseModel):
    inventory_id: UUID


class StoreInventory(BaseModel):
    email: str
    name: str  # TODO distinguish between user name and inventory name
    address: str
    quantity: int


class StoreInventoryResponse(BaseModel):
    inventory: List[StoreInventory]
