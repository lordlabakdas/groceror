from datetime import datetime
from typing import Optional
from uuid import UUID
from sqlmodel import SQLModel, Field


class User(SQLModel, table=True):
    id: Optional[UUID] = Field(default=None, primary_key=True)
    name: str
    email: str
    entity_type: Optional[str] = None
    username: str
    password: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    location: Optional[str] = None
