from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel


class StockThreshold(SQLModel, table=True):
    __tablename__ = "stockthreshold"

    id: Optional[UUID] = Field(default_factory=uuid4, primary_key=True)
    inventory_id: UUID = Field(foreign_key="inventory.id", unique=True, index=True)
    threshold: int
    is_triggered: bool = Field(default=False)
    triggered_at: Optional[datetime] = None
    acknowledged_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
