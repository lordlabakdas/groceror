from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel


class OrderItem(SQLModel, table=True):
    __tablename__ = "orderitem"

    id: Optional[UUID] = Field(default_factory=uuid4, primary_key=True)
    order_id: UUID = Field(foreign_key="order.id", index=True)
    inventory_id: UUID = Field(foreign_key="inventory.id", index=True)
    quantity: int = Field(default=1)
    price: float = Field(default=0.0)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
