from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel


class Order(SQLModel, table=True):
    id: Optional[UUID] = Field(default_factory=uuid4, primary_key=True)
    # order_id kept for DB-schema compatibility (pre-existing NOT NULL column)
    order_id: UUID = Field(default_factory=uuid4)
    user_id: UUID = Field(foreign_key="user.id", index=True)
    store_id: Optional[UUID] = Field(default=None, foreign_key="store.id", index=True)
    total_price: float = Field(default=0.0)
    status: str = Field(default="pending", index=True)
    order_date: datetime = Field(default_factory=datetime.utcnow)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
