from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel

# status flow: open → store_responded → resolved | closed
# resolution set when status = resolved
DISPUTE_STATUSES = {"open", "store_responded", "resolved", "closed"}
DISPUTE_RESOLUTIONS = {"refund", "replacement", "rejected", "no_action"}


class Dispute(SQLModel, table=True):
    __tablename__ = "dispute"

    id: Optional[UUID] = Field(default_factory=uuid4, primary_key=True)
    order_id: UUID = Field(foreign_key="order.id", index=True)
    user_id: UUID = Field(foreign_key="user.id", index=True)
    store_id: UUID = Field(foreign_key="store.id", index=True)
    reason: str                           # e.g. "wrong_item", "missing_item", "quality"
    description: str
    status: str = Field(default="open")
    resolution: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
