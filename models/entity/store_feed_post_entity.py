from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel


class StoreFeedPost(SQLModel, table=True):
    __tablename__ = "storefeedpost"

    id: Optional[UUID] = Field(default_factory=uuid4, primary_key=True)
    store_id: UUID = Field(foreign_key="store.id", index=True)
    update_type: str  # "coupon" | "promotion" | "flash_sale" | "announcement"
    message: str
    ref_id: Optional[UUID] = None  # id of the Coupon/Promotion/FlashSale this refers to, if any
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)
