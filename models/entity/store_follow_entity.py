from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel, UniqueConstraint


class StoreFollow(SQLModel, table=True):
    __tablename__ = "storefollow"
    __table_args__ = (UniqueConstraint("user_id", "store_id", name="uq_storefollow_user_store"),)

    id: Optional[UUID] = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="user.id", index=True)
    store_id: UUID = Field(foreign_key="store.id", index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
