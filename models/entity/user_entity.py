import uuid
from datetime import datetime
from enum import Enum
from typing import List, Optional

from sqlmodel import Field, Relationship, SQLModel


class UserType(str, Enum):
    ADMIN = "admin"
    USER = "user"
    STORE = "store"


class User(SQLModel, table=True):
    id: Optional[uuid.UUID] = Field(default_factory=uuid.uuid4, primary_key=True)
    name: str
    email: str
    entity_id: uuid.UUID = Field(foreign_key="phoneverification.id")
    location: Optional[str] = None
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)
    updated_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)
    