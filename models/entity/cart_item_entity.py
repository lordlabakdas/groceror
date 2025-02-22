from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4
from sqlmodel import Field, SQLModel


class CartItemEntity(SQLModel, table=True):
    id: Optional[UUID] = Field(default_factory=uuid4, primary_key=True)
    cart_id: UUID = Field(foreign_key="cartentity.id")
    inventory_id: UUID = Field(foreign_key="inventory.id")
    quantity: int = Field(default=1)
    price: float = Field(default=0.0)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    notes: Optional[str] = None
