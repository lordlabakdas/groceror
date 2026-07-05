from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel


class LoyaltyAccount(SQLModel, table=True):
    __tablename__ = "loyaltyaccount"

    id: Optional[UUID] = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="user.id", unique=True, index=True)
    points_balance: int = Field(default=0)
    total_earned: int = Field(default=0)
    total_redeemed: int = Field(default=0)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
