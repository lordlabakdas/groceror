from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel


class InventoryReservation(SQLModel, table=True):
    __tablename__ = "inventoryreservation"

    id: Optional[UUID] = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="user.id", index=True)
    cart_id: UUID = Field(foreign_key="cartentity.id", index=True)
    inventory_id: UUID = Field(foreign_key="inventory.id", index=True)
    quantity: int = Field(gt=0)
    status: str = Field(default="active", index=True)
    expires_at: datetime = Field(index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
