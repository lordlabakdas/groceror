from datetime import datetime
from typing import Dict, List, Optional
from uuid import UUID, uuid4
from sqlalchemy import ARRAY, JSON, Column, String
from sqlmodel import Field, SQLModel, table


class Order(SQLModel, table=True):
    id: Optional[UUID] = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="user.id")
    total_price: float = Field(default=0.0)
    status: str = Field(default="pending")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    items: List[str] = Field(sa_column=Column(ARRAY(String)))
    order_id: UUID = Field(default_factory=uuid4)
    order_date: datetime = Field(default_factory=datetime.utcnow)
