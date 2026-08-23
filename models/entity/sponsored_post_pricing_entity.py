from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel


class SponsoredPostPricing(SQLModel, table=True):
    """Append-only price history for the flat per-post sponsored-post fee.
    Same shape and rationale as SubscriptionPlan (SPEC_SUBSCRIPTION.md §3.1):
    the current price is the most recent row; never mutated in place, so a
    price change doesn't touch any SponsoredPost already created. See
    SPEC_SPONSORED_POSTS.md §3.1."""

    __tablename__ = "sponsoredpostpricing"

    id: Optional[UUID] = Field(default_factory=uuid4, primary_key=True)
    price_paise: int
    created_at: datetime = Field(default_factory=datetime.utcnow)
    created_by: str = Field(default="admin")
