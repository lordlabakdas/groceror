from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, validator

from models.entity.inventory_entity import InventoryCategory


class AddInventoryPayload(BaseModel):
    name: str
    quantity: int
    category: InventoryCategory
    price: float = 0.0
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
    id: UUID
    name: str
    quantity: int
    category: InventoryCategory
    price: float
    store_id: UUID
    notes: Optional[str] = None


class StoreInventoryResponse(BaseModel):
    inventory: List[StoreInventory]


class DeleteInventoryResponse(BaseModel):
    status: str
