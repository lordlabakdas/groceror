from datetime import date, datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel


class Coupon(SQLModel, table=True):
    __tablename__ = "coupon"

    id: Optional[UUID] = Field(default_factory=uuid4, primary_key=True)
    code: str = Field(unique=True, index=True)        # uppercase, e.g. "SAVE10"
    discount_type: str                                 # "percent" | "fixed"
    discount_value: float                              # 0-100 for percent, dollar amount for fixed
    min_order_amount: Optional[float] = None           # minimum subtotal to apply
    max_uses: Optional[int] = None                     # None = unlimited
    uses_count: int = Field(default=0)
    store_id: Optional[UUID] = Field(default=None, foreign_key="store.id", index=True)
    valid_from: Optional[date] = None
    valid_until: Optional[date] = None
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
