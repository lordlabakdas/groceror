from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel


class SubscriptionPlan(SQLModel, table=True):
    """Append-only price history. The current price is the most recent row
    (order by created_at desc, limit 1) — never mutated in place, so an
    admin price change doesn't touch any existing Subscription and leaves a
    free audit trail of what Groceror charged and when.
    See SPEC_SUBSCRIPTION.md §3.1, §3.5."""

    __tablename__ = "subscriptionplan"

    id: Optional[UUID] = Field(default_factory=uuid4, primary_key=True)
    price_paise: int
    # Set once the Razorpay Plan for this price has actually been created
    # (lazily, on first checkout at this price — see SPEC_SUBSCRIPTION.md §3.4).
    razorpay_plan_id: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    # Informational only — X-Admin-Token has no per-admin identity.
    created_by: str = Field(default="admin")
