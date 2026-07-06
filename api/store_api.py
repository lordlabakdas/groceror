from collections import defaultdict
from datetime import datetime
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field as PydanticField
from sqlmodel import select

from helpers.jwt import auth_required
from models.db import db_session
from models.entity.phone_verification import PhoneVerification
from models.entity.store_entity import Store
from models.entity.store_rating_entity import StoreRating
from models.entity.user_entity import User
from models.service.store_service import StoreService

store_apis = APIRouter(prefix="/stores", tags=["stores"])


class StoreCreate(BaseModel):
    name: str
    email: str
    website: Optional[str] = None
    location: Optional[str] = None


class StoreUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    website: Optional[str] = None
    location: Optional[str] = None


class SubmitRatingPayload(BaseModel):
    rating: int = PydanticField(ge=1, le=5)
    comment: Optional[str] = None


class RatingItem(BaseModel):
    id: UUID
    rating: int
    comment: Optional[str]
    created_at: datetime


class RatingSummaryResponse(BaseModel):
    avg_rating: Optional[float]
    rating_count: int
    ratings: List[RatingItem]


def _assert_owner(store, current_user: PhoneVerification):
    if store.entity_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to modify this store",
        )


def _store_to_dict(store: Store, avg_rating=None, rating_count=0):
    return {
        "id": store.id,
        "name": store.name,
        "email": store.email,
        "location": store.location,
        "website": store.website,
        "is_active": store.is_active,
        "latitude": store.latitude,
        "longitude": store.longitude,
        "avg_rating": avg_rating,
        "rating_count": rating_count,
    }


@store_apis.post("/", status_code=status.HTTP_201_CREATED)
async def create_store(
    store_data: StoreCreate,
    current_user: PhoneVerification = Depends(auth_required),
):
    store_service = StoreService()
    return store_service.create_store(entity_id=current_user.id, **store_data.model_dump())


@store_apis.get("/")
async def list_all_stores(
    current_user: PhoneVerification = Depends(auth_required),
):
    store_service = StoreService()
    stores = store_service.get_all_active_stores()
    if not stores:
        return []

    store_ids = [s.id for s in stores]
    ratings = db_session.exec(
        select(StoreRating).where(StoreRating.store_id.in_(store_ids))
    ).all()

    ratings_by_store: dict = defaultdict(list)
    for r in ratings:
        ratings_by_store[r.store_id].append(r.rating)

    result = []
    for store in stores:
        store_ratings = ratings_by_store.get(store.id, [])
        avg = round(sum(store_ratings) / len(store_ratings), 1) if store_ratings else None
        result.append(_store_to_dict(store, avg_rating=avg, rating_count=len(store_ratings)))
    return result


@store_apis.get("/search/{query}")
async def search_stores(
    query: str,
    current_user: PhoneVerification = Depends(auth_required),
):
    store_service = StoreService()
    return store_service.search_stores(query)


@store_apis.get("/my-stores")
async def get_my_stores(current_user: PhoneVerification = Depends(auth_required)):
    store_service = StoreService()
    return store_service.get_stores_by_entity(current_user.id)


@store_apis.get("/{store_id}/ratings", response_model=RatingSummaryResponse)
async def get_store_ratings(
    store_id: UUID,
    current_user: PhoneVerification = Depends(auth_required),
):
    ratings = db_session.exec(
        select(StoreRating)
        .where(StoreRating.store_id == store_id)
        .order_by(StoreRating.created_at.desc())
    ).all()

    avg = round(sum(r.rating for r in ratings) / len(ratings), 1) if ratings else None
    return RatingSummaryResponse(
        avg_rating=avg,
        rating_count=len(ratings),
        ratings=[
            RatingItem(id=r.id, rating=r.rating, comment=r.comment, created_at=r.created_at)
            for r in ratings
        ],
    )


@store_apis.post("/{store_id}/ratings")
async def submit_rating(
    store_id: UUID,
    payload: SubmitRatingPayload,
    current_user: PhoneVerification = Depends(auth_required),
):
    if current_user.entity_type != "user":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only shoppers can submit ratings",
        )
    user = db_session.exec(select(User).where(User.entity_id == current_user.id)).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User profile not set")
    store = db_session.exec(select(Store).where(Store.id == store_id)).first()
    if not store:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Store not found")

    existing = db_session.exec(
        select(StoreRating).where(
            StoreRating.store_id == store_id,
            StoreRating.user_id == user.id,
        )
    ).first()
    if existing:
        existing.rating = payload.rating
        existing.comment = payload.comment
        existing.updated_at = datetime.utcnow()
    else:
        db_session.add(StoreRating(
            store_id=store_id,
            user_id=user.id,
            rating=payload.rating,
            comment=payload.comment,
        ))
    db_session.commit()
    return {"status": "success"}


@store_apis.get("/{store_id}")
async def get_store(
    store_id: UUID,
    current_user: PhoneVerification = Depends(auth_required),
):
    store_service = StoreService()
    store = store_service.get_store(store_id)

    ratings = db_session.exec(
        select(StoreRating).where(StoreRating.store_id == store_id)
    ).all()
    avg = round(sum(r.rating for r in ratings) / len(ratings), 1) if ratings else None
    return _store_to_dict(store, avg_rating=avg, rating_count=len(ratings))


@store_apis.put("/{store_id}")
async def update_store(
    store_id: UUID,
    store_data: StoreUpdate,
    current_user: PhoneVerification = Depends(auth_required),
):
    store_service = StoreService()
    _assert_owner(store_service.get_store(store_id), current_user)
    return store_service.update_store(store_id, **store_data.model_dump(exclude_unset=True))


@store_apis.delete("/{store_id}")
async def delete_store(
    store_id: UUID,
    current_user: PhoneVerification = Depends(auth_required),
):
    store_service = StoreService()
    _assert_owner(store_service.get_store(store_id), current_user)
    return store_service.delete_store(store_id)


@store_apis.post("/{store_id}/deactivate")
async def deactivate_store(
    store_id: UUID,
    current_user: PhoneVerification = Depends(auth_required),
):
    store_service = StoreService()
    _assert_owner(store_service.get_store(store_id), current_user)
    return store_service.deactivate_store(store_id)


@store_apis.post("/{store_id}/activate")
async def activate_store(
    store_id: UUID,
    current_user: PhoneVerification = Depends(auth_required),
):
    store_service = StoreService()
    _assert_owner(store_service.get_store(store_id), current_user)
    return store_service.activate_store(store_id)


# ── Admin: store verification ───────────────────────────────────────────────

from fastapi import Header
from config import AdminConfig


def _require_admin(x_admin_token: str = Header(...)):
    if x_admin_token != AdminConfig.ADMIN_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid admin token")


@store_apis.post("/{store_id}/verify", status_code=200)
def verify_store(store_id: UUID, _: None = Depends(_require_admin)):
    store = db_session.exec(select(Store).where(Store.id == store_id)).first()
    if not store:
        raise HTTPException(status_code=404, detail="Store not found")
    store.is_verified = True
    db_session.add(store)
    db_session.commit()
    return {"status": "verified"}


@store_apis.delete("/{store_id}/verify", status_code=200)
def unverify_store(store_id: UUID, _: None = Depends(_require_admin)):
    store = db_session.exec(select(Store).where(Store.id == store_id)).first()
    if not store:
        raise HTTPException(status_code=404, detail="Store not found")
    store.is_verified = False
    db_session.add(store)
    db_session.commit()
    return {"status": "unverified"}
