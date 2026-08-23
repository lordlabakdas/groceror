from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel


class SponsoredPost(SQLModel, table=True):
    """One row per paid broadcast attempt. Created in status="pending" at
    checkout time, before any money has moved — only becomes visible in
    anyone's feed once confirm() marks it "paid" and creates the
    corresponding StoreFeedPost (feed_post_id). See SPEC_SPONSORED_POSTS.md
    §3.1/§3.3."""

    __tablename__ = "sponsoredpost"

    id: Optional[UUID] = Field(default_factory=uuid4, primary_key=True)
    store_id: UUID = Field(foreign_key="store.id", index=True)
    message: str
    amount_paise: int  # snapshotted SponsoredPostPricing price at checkout
    status: str = Field(default="pending", index=True)  # pending | paid | failed
    razorpay_order_id: Optional[str] = None
    razorpay_payment_id: Optional[str] = None
    feed_post_id: Optional[UUID] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    paid_at: Optional[datetime] = None
