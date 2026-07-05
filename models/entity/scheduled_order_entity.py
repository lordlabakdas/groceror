from datetime import date, datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel

FREQUENCIES = {"weekly": 7, "biweekly": 14, "monthly": 30}


class ScheduledOrder(SQLModel, table=True):
    __tablename__ = "scheduledorder"

    id: Optional[UUID] = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="user.id", index=True)
    store_id: UUID = Field(foreign_key="store.id", index=True)
    store_name: str                 # denormalized for display
    frequency: str                  # "weekly" | "biweekly" | "monthly"
    next_run_date: date
    is_active: bool = Field(default=True)
    last_run_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
