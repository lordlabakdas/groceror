from enum import Enum
import uuid
from datetime import datetime
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
    entity_type: Optional[str] = None
    username: str
    password: str
    is_verified: bool = Field(default=False)
    verification_token: Optional[str] = Field(default=None)
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)
    updated_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)
    location: Optional[str] = None
    # inventory: List["Inventory"] = Relationship(back_populates="user")
