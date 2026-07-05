from datetime import datetime
from uuid import UUID, uuid4
from typing import Optional

from sqlmodel import Field, SQLModel


class DisputeMessage(SQLModel, table=True):
    __tablename__ = "disputemessage"

    id: Optional[UUID] = Field(default_factory=uuid4, primary_key=True)
    dispute_id: UUID = Field(foreign_key="dispute.id", index=True)
    sender_type: str              # "shopper" | "store"
    message: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
