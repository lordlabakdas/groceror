from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel


class LoyaltyTransaction(SQLModel, table=True):
    __tablename__ = "loyaltytransaction"

    id: Optional[UUID] = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="user.id", index=True)
    order_id: Optional[UUID] = Field(default=None, foreign_key="order.id")
    points: int                    # positive = earned, negative = redeemed
    transaction_type: str          # "earned" | "redeemed" | "adjusted"
    description: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
