from datetime import date, datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel


class Promotion(SQLModel, table=True):
    id: Optional[UUID] = Field(default_factory=uuid4, primary_key=True)
    inventory_id: UUID = Field(foreign_key="inventory.id", unique=True, index=True)
    sale_price: float
    start_date: date
    end_date: date
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
