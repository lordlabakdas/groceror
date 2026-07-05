from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel


class PriceAlert(SQLModel, table=True):
    __tablename__ = "pricealert"

    id: Optional[UUID] = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="user.id", index=True)
    inventory_id: UUID = Field(foreign_key="inventory.id", index=True)
    target_price: float
    is_active: bool = Field(default=True)
    is_triggered: bool = Field(default=False)
    triggered_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
