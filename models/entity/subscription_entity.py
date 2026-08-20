from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel

# trialing -> active (first charge) | grace (trial lapses unauthorized)
# active   -> grace (payment fails / pending)
# grace    -> active (payment succeeds) | locked (grace period expires)
# locked   -> active (payment succeeds)
# any      -> cancelled
# See SPEC_SUBSCRIPTION.md §3.2.
SUBSCRIPTION_STATUSES = {"trialing", "active", "grace", "locked", "cancelled"}


class Subscription(SQLModel, table=True):
    __tablename__ = "subscription"

    id: Optional[UUID] = Field(default_factory=uuid4, primary_key=True)
    store_id: UUID = Field(foreign_key="store.id", unique=True, index=True)
    status: str = Field(default="trialing", index=True)
    razorpay_customer_id: Optional[str] = None
    razorpay_subscription_id: Optional[str] = None
    # Snapshotted at checkout from the then-current SubscriptionPlan — null
    # during trialing, before the store owner has checked out at all.
    plan_price_paise: Optional[int] = None
    trial_end: datetime
    current_period_start: Optional[datetime] = None
    current_period_end: Optional[datetime] = None
    grace_period_end: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
