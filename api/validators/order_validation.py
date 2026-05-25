from datetime import datetime
from pydantic import BaseModel, Field

from typing import List, Optional
from uuid import UUID, uuid4

VALID_STATUSES = {"pending", "confirmed", "ready", "delivered", "cancelled"}


class Order(BaseModel):
    items: List[UUID]
    total_price: float
    status: str
    order_date: datetime = Field(default_factory=datetime.utcnow)


class OrderHistoryItem(BaseModel):
    id: UUID
    total_price: float
    status: str
    items: List[str]
    order_date: datetime


class OrderHistoryResponse(BaseModel):
    orders: List[OrderHistoryItem]


class StoreOrderItem(BaseModel):
    id: UUID
    total_price: float
    status: str
    item_names: List[str]
    order_date: datetime


class StoreOrdersResponse(BaseModel):
    orders: List[StoreOrderItem]


class UpdateOrderStatusPayload(BaseModel):
    status: str


class UpdateOrderStatusResponse(BaseModel):
    message: str
    status: str
