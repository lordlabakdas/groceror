from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel


class FeedReadState(SQLModel, table=True):
    __tablename__ = "feedreadstate"

    id: Optional[UUID] = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="user.id", index=True, unique=True)
    last_read_at: datetime = Field(default_factory=datetime.utcnow)
