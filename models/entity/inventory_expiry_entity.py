from datetime import date, datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel


class InventoryExpiry(SQLModel, table=True):
    __tablename__ = "inventoryexpiry"

    id: Optional[UUID] = Field(default_factory=uuid4, primary_key=True)
    inventory_id: UUID = Field(foreign_key="inventory.id", index=True)
    expiry_date: date
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
