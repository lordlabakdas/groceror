import logging
from datetime import datetime
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlmodel import select

from helpers.jwt import auth_required
from models.db import db_session
from models.entity.loyalty_account_entity import LoyaltyAccount
from models.entity.loyalty_transaction_entity import LoyaltyTransaction
from models.entity.phone_verification import PhoneVerification
from models.entity.user_entity import User

logger = logging.getLogger(__name__)
loyalty_apis = APIRouter(prefix="/loyalty", tags=["loyalty"])

# 100 points = $1 — same constant as in orders_service
POINTS_PER_DOLLAR_REDEMPTION = 100


def _get_user(entity: PhoneVerification = Depends(auth_required)) -> User:
    user = db_session.exec(select(User).where(User.entity_id == entity.id)).first()
    if not user:
        raise HTTPException(status_code=400, detail="User profile not set. Call /user/set-profile first.")
    return user


class LoyaltyBalanceResponse(BaseModel):
    points_balance: int
    total_earned: int
    total_redeemed: int
    dollar_value: float        # how much the current balance is worth in $


class LoyaltyTransactionItem(BaseModel):
    id: UUID
    order_id: Optional[UUID]
    points: int
    transaction_type: str
    description: str
    created_at: datetime


class LoyaltyHistoryResponse(BaseModel):
    transactions: List[LoyaltyTransactionItem]


@loyalty_apis.get("/balance", response_model=LoyaltyBalanceResponse)
async def get_loyalty_balance(current_user: User = Depends(_get_user)):
    acct = db_session.exec(
        select(LoyaltyAccount).where(LoyaltyAccount.user_id == current_user.id)
    ).first()
    if not acct:
        return LoyaltyBalanceResponse(
            points_balance=0, total_earned=0, total_redeemed=0, dollar_value=0.0
        )
    return LoyaltyBalanceResponse(
        points_balance=acct.points_balance,
        total_earned=acct.total_earned,
        total_redeemed=acct.total_redeemed,
        dollar_value=round(acct.points_balance / POINTS_PER_DOLLAR_REDEMPTION, 2),
    )


@loyalty_apis.get("/history", response_model=LoyaltyHistoryResponse)
async def get_loyalty_history(current_user: User = Depends(_get_user)):
    txns = db_session.exec(
        select(LoyaltyTransaction)
        .where(LoyaltyTransaction.user_id == current_user.id)
        .order_by(LoyaltyTransaction.created_at.desc())
    ).all()
    return LoyaltyHistoryResponse(
        transactions=[
            LoyaltyTransactionItem(
                id=t.id,
                order_id=t.order_id,
                points=t.points,
                transaction_type=t.transaction_type,
                description=t.description,
                created_at=t.created_at,
            )
            for t in txns
        ]
    )
