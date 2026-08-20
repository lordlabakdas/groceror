from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel


class SubscriptionInvoice(SQLModel, table=True):
    __tablename__ = "subscriptioninvoice"

    id: Optional[UUID] = Field(default_factory=uuid4, primary_key=True)
    subscription_id: UUID = Field(foreign_key="subscription.id", index=True)
    razorpay_payment_id: Optional[str] = None
    amount_paise: int
    status: str  # paid / failed
    period_start: datetime
    period_end: datetime
    paid_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
