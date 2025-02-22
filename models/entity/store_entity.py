from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4
from sqlmodel import Field, Relationship, SQLModel

from models.entity.user_entity import User


class Store(SQLModel, table=True):
    id: Optional[UUID] = Field(default_factory=uuid4, primary_key=True)
    name: str = Field(index=True)
    user_id: UUID = Field(foreign_key="user.id")
    # user: User = Relationship(back_populates="stores")
    address: str = Field(index=True)
    phone: str = Field(index=True)
    email: str = Field(index=True)
    website: str = Field(index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    is_active: bool = Field(default=True)

    def __repr__(self):
        return f"<Store(id={self.id}, name={self.name})>"

    def __str__(self):
        return self.name

    def __hash__(self):
        return hash(self.id)

    def is_active(self):
        return self.is_active

    def is_inactive(self):
        return not self.is_active

    def get_email(self):
        return self.email

    def get_phone(self):
        return self.phone
