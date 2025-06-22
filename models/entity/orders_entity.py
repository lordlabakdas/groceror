from datetime import datetime
from typing import Dict, List, Optional
from uuid import UUID, uuid4
from sqlmodel import Field, SQLModel


class Order(SQLModel):
    id: Optional[UUID] = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="user.id")
    total_price: float = Field(default=0.0)
    status: str = Field(default="pending")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    items: List[UUID] = Field(default_factory=list)
    order_id: UUID = Field(default_factory=uuid4)
    order_date: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        orm_mode = True
