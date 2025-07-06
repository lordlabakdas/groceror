from datetime import datetime
from pydantic import BaseModel, Field

from typing import List
from uuid import UUID, uuid4


class Order(BaseModel):
    items: List[UUID]
    total_price: float
    status: str
    order_date: datetime = Field(default_factory=datetime.utcnow)
