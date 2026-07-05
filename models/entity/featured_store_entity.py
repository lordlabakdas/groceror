from datetime import date, datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel


class FeaturedStore(SQLModel, table=True):
    __tablename__ = "featuredstore"

    id: Optional[UUID] = Field(default_factory=uuid4, primary_key=True)
    store_id: UUID = Field(foreign_key="store.id", unique=True, index=True)
    tagline: Optional[str] = None
    priority: int = Field(default=0)       # higher = shown first
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
