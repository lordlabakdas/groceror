from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel


class Order(SQLModel, table=True):
    id: Optional[UUID] = Field(default_factory=uuid4, primary_key=True)
    # order_id kept for DB-schema compatibility (pre-existing NOT NULL column)
    order_id: UUID = Field(default_factory=uuid4)
    user_id: UUID = Field(foreign_key="user.id", index=True)
    store_id: Optional[UUID] = Field(default=None, foreign_key="store.id", index=True)
    total_price: float = Field(default=0.0)
    discount_amount: float = Field(default=0.0)
    points_redeemed: int = Field(default=0)
    coupon_code: Optional[str] = Field(default=None)
    status: str = Field(default="pending", index=True)
    order_date: datetime = Field(default_factory=datetime.utcnow)
    # Delivery dispatch fields (see SPEC_DELIVERY_DISPATCH.md §3.3). All nullable:
    # a pickup-only order never sets these. delivery_fee is folded into total_price
    # at creation time, kept here too so it can be broken out in order history/receipts.
    delivery_fee: Optional[float] = Field(default=None)
    delivery_address_line: Optional[str] = Field(default=None)
    delivery_lat: Optional[float] = Field(default=None)
    delivery_lng: Optional[float] = Field(default=None)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
