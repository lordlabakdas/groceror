from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel, UniqueConstraint


class StoreRating(SQLModel, table=True):
    __tablename__ = "storerating"
    __table_args__ = (UniqueConstraint("store_id", "user_id", name="uq_store_rating_user"),)

    id: Optional[UUID] = Field(default_factory=uuid4, primary_key=True)
    store_id: UUID = Field(foreign_key="store.id", index=True)
    user_id: UUID = Field(foreign_key="user.id", index=True)
    rating: int  # 1–5
    comment: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
