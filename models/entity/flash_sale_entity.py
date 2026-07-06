from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel


class FlashSale(SQLModel, table=True):
    __tablename__ = "flashsale"

    id: Optional[UUID] = Field(default_factory=uuid4, primary_key=True)
    inventory_id: UUID = Field(foreign_key="inventory.id", index=True)
    store_id: UUID = Field(foreign_key="store.id", index=True)
    sale_price: float
    start_at: datetime
    end_at: datetime
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
