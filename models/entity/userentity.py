from typing import Optional
from uuid import UUID

from sqlmodel import Field, SQLModel


class User(SQLModel, table=True):
    id: Optional[UUID] = Field(default=None, primary_key=True)
    name: str
