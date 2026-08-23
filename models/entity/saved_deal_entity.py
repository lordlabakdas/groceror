from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel, UniqueConstraint


class SavedDeal(SQLModel, table=True):
    """A shopper's bookmark of a coupon/promotion/flash_sale feed item.
    See SPEC_SAVED_DEALS.md. References the StoreFeedPost the shopper
    clicked, not the underlying Coupon/Promotion/FlashSale directly —
    freshness is resolved from that source at read time."""

    __tablename__ = "saveddeal"
    __table_args__ = (UniqueConstraint("user_id", "feed_post_id", name="uq_saveddeal_user_feedpost"),)

    id: Optional[UUID] = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="user.id", index=True)
    feed_post_id: UUID = Field(foreign_key="storefeedpost.id", index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
