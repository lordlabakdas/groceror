from typing import Optional
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel


class ScheduledOrderItem(SQLModel, table=True):
    __tablename__ = "scheduledorderitem"

    id: Optional[UUID] = Field(default_factory=uuid4, primary_key=True)
    scheduled_order_id: UUID = Field(foreign_key="scheduledorder.id", index=True)
    inventory_id: UUID = Field(foreign_key="inventory.id")
    quantity: int = Field(default=1)
    item_name: str                  # captured at schedule creation time
