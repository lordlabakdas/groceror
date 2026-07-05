# api/validators/order_validation.py
from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field

VALID_STATUSES = {"pending", "confirmed", "ready", "delivered", "cancelled"}


class OrderLineItem(BaseModel):
    inventory_id: UUID
    quantity: int = 1


class CreateOrderRequest(BaseModel):
    items: List[OrderLineItem] = Field(..., min_length=1)
    order_date: datetime = Field(default_factory=datetime.utcnow)
    coupon_code: Optional[str] = None
    points_to_redeem: int = Field(default=0, ge=0)


class OrderCreatedResponse(BaseModel):
    id: UUID
    status: str
    total_price: float
    discount_amount: float
    points_earned: int


class OrderHistoryLineItem(BaseModel):
    inventory_id: UUID
    name: str
    quantity: int
    price: float


class OrderHistoryItem(BaseModel):
    id: UUID
    total_price: float
    discount_amount: float = 0.0
    points_redeemed: int = 0
    coupon_code: Optional[str] = None
    status: str
    items: List[OrderHistoryLineItem]
    order_date: datetime
    store_id: Optional[UUID] = None
    store_name: Optional[str] = None


class OrderHistoryResponse(BaseModel):
    orders: List[OrderHistoryItem]


class StoreOrderLineItem(BaseModel):
    inventory_id: UUID
    name: str
    quantity: int
    price: float


class StoreOrderItem(BaseModel):
    id: UUID
    total_price: float
    status: str
    items: List[StoreOrderLineItem]
    order_date: datetime


class StoreOrdersResponse(BaseModel):
    orders: List[StoreOrderItem]


class UpdateOrderStatusPayload(BaseModel):
    status: str


class UpdateOrderStatusResponse(BaseModel):
    message: str
    status: str
