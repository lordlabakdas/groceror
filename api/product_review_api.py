from datetime import datetime
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field as PField
from sqlalchemy import func
from sqlmodel import select

from helpers.jwt import auth_required
from models.db import db_session
from models.entity.inventory_entity import Inventory
from models.entity.phone_verification import PhoneVerification
from models.entity.product_review_entity import ProductReview
from models.entity.user_entity import User

product_review_apis = APIRouter(prefix="/product-reviews", tags=["product-reviews"])


def _get_user(entity: PhoneVerification = Depends(auth_required)) -> User:
    user = db_session.exec(select(User).where(User.entity_id == entity.id)).first()
    if not user:
        raise HTTPException(status_code=400, detail="User profile not set")
    return user


class SubmitReviewPayload(BaseModel):
    inventory_id: UUID
    rating: int = PField(..., ge=1, le=5)
    comment: Optional[str] = None


class ReviewResponse(BaseModel):
    id: UUID
    user_id: UUID
    inventory_id: UUID
    rating: int
    comment: Optional[str]
    created_at: datetime
    updated_at: datetime


class ReviewSummaryResponse(BaseModel):
    avg_rating: Optional[float]
    review_count: int
    reviews: List[ReviewResponse]
    my_review: Optional[ReviewResponse]


def _to_response(r: ProductReview) -> ReviewResponse:
    return ReviewResponse(
        id=r.id,
        user_id=r.user_id,
        inventory_id=r.inventory_id,
        rating=r.rating,
        comment=r.comment,
        created_at=r.created_at,
        updated_at=r.updated_at,
    )


@product_review_apis.post("", response_model=ReviewResponse)
def submit_review(payload: SubmitReviewPayload, user: User = Depends(_get_user)):
    inv = db_session.exec(select(Inventory).where(Inventory.id == payload.inventory_id)).first()
    if not inv:
        raise HTTPException(status_code=404, detail="Item not found")

    existing = db_session.exec(
        select(ProductReview).where(
            ProductReview.user_id == user.id,
            ProductReview.inventory_id == payload.inventory_id,
        )
    ).first()

    if existing:
        existing.rating = payload.rating
        existing.comment = payload.comment
        existing.updated_at = datetime.utcnow()
        db_session.add(existing)
        db_session.commit()
        db_session.refresh(existing)
        return _to_response(existing)

    review = ProductReview(
        user_id=user.id,
        inventory_id=payload.inventory_id,
        store_id=inv.store_id,
        rating=payload.rating,
        comment=payload.comment,
    )
    db_session.add(review)
    db_session.commit()
    db_session.refresh(review)
    return _to_response(review)


@product_review_apis.get("/{inventory_id}", response_model=ReviewSummaryResponse)
def get_reviews(inventory_id: UUID, entity: Optional[PhoneVerification] = Depends(auth_required)):
    reviews = db_session.exec(
        select(ProductReview)
        .where(ProductReview.inventory_id == inventory_id)
        .order_by(ProductReview.created_at.desc())
    ).all()

    avg = None
    if reviews:
        avg = round(sum(r.rating for r in reviews) / len(reviews), 2)

    my_review = None
    if entity:
        user = db_session.exec(select(User).where(User.entity_id == entity.id)).first()
        if user:
            my_review = next((r for r in reviews if r.user_id == user.id), None)

    return ReviewSummaryResponse(
        avg_rating=avg,
        review_count=len(reviews),
        reviews=[_to_response(r) for r in reviews],
        my_review=_to_response(my_review) if my_review else None,
    )


@product_review_apis.delete("/{review_id}", status_code=204)
def delete_review(review_id: UUID, user: User = Depends(_get_user)):
    review = db_session.exec(
        select(ProductReview).where(
            ProductReview.id == review_id,
            ProductReview.user_id == user.id,
        )
    ).first()
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    db_session.delete(review)
    db_session.commit()
