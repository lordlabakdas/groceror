import datetime
from typing import Optional
from uuid import UUID

from sqlmodel import Column, Field, SQLModel


class User(SQLModel, table=True):
    id: Optional[UUID] = Field(default=None, primary_key=True)
    name: str
    email: str
    address: str
    entity_type: str
    username: str
    password: str
    created_at: datetime = Column(nullable=False, default=datetime.datetime.utcnow)
    updated_at: datetime = Column(
        nullable=False, default=datetime.utcnow, onupdate=datetime.datetime.utcnow
    )
    location: str
