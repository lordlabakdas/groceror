from datetime import datetime
from typing import Optional, List
from uuid import UUID, uuid4
from sqlmodel import Field, SQLModel
from models.entity.cart_item_entity import CartItemEntity


class CartEntity(SQLModel, table=True   ):
    id: Optional[UUID] = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="user.id")
    items: List[CartItemEntity] = Field(default=[])
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    total_price: float = Field(default=0.0)
    total_quantity: int = Field(default=0)
    notes: Optional[str] = None
