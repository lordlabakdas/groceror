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
    # Absent = pickup order, no delivery. See SPEC_DELIVERY_DISPATCH.md §3.3
    # for why this re-quotes server-side rather than taking a client-supplied
    # fee or quote_id.
    delivery_address_line: Optional[str] = None
    delivery_lat: Optional[float] = None
    delivery_lng: Optional[float] = None


class OrderCreatedResponse(BaseModel):
    id: UUID
    status: str
    total_price: float
    discount_amount: float
    points_earned: int
    delivery_fee: Optional[float] = None


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
    # None = pickup order (no delivery requested). See SPEC_DELIVERY_DISPATCH.md.
    delivery_fee: Optional[float] = None
    delivery_status: Optional[str] = None


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
    # None = pickup order (no delivery requested). See SPEC_DELIVERY_DISPATCH.md.
    delivery_fee: Optional[float] = None
    delivery_status: Optional[str] = None


class StoreOrdersResponse(BaseModel):
    orders: List[StoreOrderItem]


class UpdateOrderStatusPayload(BaseModel):
    status: str


class UpdateOrderStatusResponse(BaseModel):
    message: str
    status: str


# ── Delivery dispatch (see SPEC_DELIVERY_DISPATCH.md) ──────────────────────


class DeliveryQuoteRequest(BaseModel):
    store_id: UUID
    dropoff_lat: float
    dropoff_lng: float


class DeliveryQuoteResponse(BaseModel):
    quote_id: str
    fee: float
    expires_at: datetime


class RequestDeliveryResponse(BaseModel):
    delivery_id: UUID
    status: str
    quoted_fee: float
