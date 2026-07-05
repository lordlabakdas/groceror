from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel, UniqueConstraint


class ProductReview(SQLModel, table=True):
    __tablename__ = "productreview"
    __table_args__ = (UniqueConstraint("user_id", "inventory_id", name="uq_product_review_user_item"),)

    id: Optional[UUID] = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="user.id", index=True)
    inventory_id: UUID = Field(foreign_key="inventory.id", index=True)
    store_id: UUID = Field(foreign_key="store.id", index=True)
    rating: int                     # 1–5
    comment: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
