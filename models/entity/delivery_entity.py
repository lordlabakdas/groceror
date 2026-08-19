from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel

# status flow: quoted -> requested -> confirmed -> picked_up -> in_transit -> delivered
#              any state (other than delivered) -> failed | cancelled
# See SPEC_DELIVERY_DISPATCH.md §3.2.
DELIVERY_STATUSES = {
    "quoted",
    "requested",
    "confirmed",
    "picked_up",
    "in_transit",
    "delivered",
    "failed",
    "cancelled",
}


class Delivery(SQLModel, table=True):
    __tablename__ = "delivery"

    id: Optional[UUID] = Field(default_factory=uuid4, primary_key=True)
    order_id: UUID = Field(foreign_key="order.id", unique=True, index=True)
    store_id: UUID = Field(foreign_key="store.id", index=True)
    # Data, not an enum: keeps a future vendor swap from requiring a schema change.
    vendor: str = Field(default="shiprocket_quick")
    vendor_quote_id: Optional[str] = None
    vendor_delivery_id: Optional[str] = Field(default=None, index=True)
    status: str = Field(default="quoted", index=True)
    quoted_fee: float
    rider_name: Optional[str] = None
    rider_phone: Optional[str] = None
    tracking_url: Optional[str] = None
    requested_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    # Last raw webhook body received for this delivery, kept for debugging
    # vendor integration issues. Not parsed back out anywhere.
    raw_webhook_payload: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
