from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel

from models.entity.inventory_entity import InventoryCategory


class AddProductPayload(BaseModel):
    name: str
    category: InventoryCategory
    image_url: Optional[str] = None
    default_price: float = 0.0


class ProductItem(BaseModel):
    id: UUID
    name: str
    category: InventoryCategory
    image_url: Optional[str]
    default_price: float


class ProductResponse(BaseModel):
    product_id: UUID


class ProductListResponse(BaseModel):
    products: List[ProductItem]
