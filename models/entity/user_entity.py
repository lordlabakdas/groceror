import uuid
from datetime import datetime
from enum import Enum
from typing import Optional

from sqlmodel import Field, SQLModel


class UserType(str, Enum):
    ADMIN = "admin"
    USER = "user"
    STORE = "store"


class User(SQLModel, table=True):
    id: Optional[uuid.UUID] = Field(default_factory=uuid.uuid4, primary_key=True)
    name: str
    email: str
    entity_type: Optional[str] = None
    username: str
    password: str
    is_verified: bool = Field(default=False)
    verification_token: Optional[str] = Field(default=None)
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)
    updated_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)
    location: Optional[str] = None
    # inventory: List["Inventory"] = Relationship(back_populates="user")
