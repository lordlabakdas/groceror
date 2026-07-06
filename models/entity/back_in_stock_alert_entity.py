from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel, UniqueConstraint


class BackInStockAlert(SQLModel, table=True):
    __tablename__ = "backinstockalert"
    __table_args__ = (UniqueConstraint("user_id", "inventory_id", name="uq_backinstockalert_user_item"),)

    id: Optional[UUID] = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="user.id", index=True)
    inventory_id: UUID = Field(foreign_key="inventory.id", index=True)
    is_triggered: bool = Field(default=False)
    triggered_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
