from datetime import datetime
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import select, func

from helpers.jwt import auth_required
from models.db import db_session
from models.entity.phone_verification import PhoneVerification
from models.entity.store_entity import Store
from models.entity.store_follow_entity import StoreFollow
from models.entity.user_entity import User

store_follow_apis = APIRouter(tags=["store-follow"])


def _get_user(entity: PhoneVerification = Depends(auth_required)) -> User:
    user = db_session.exec(select(User).where(User.entity_id == entity.id)).first()
    if not user:
        raise HTTPException(status_code=400, detail="User profile not set")
    return user


class FollowedStoreResponse(BaseModel):
    store_id: UUID
    store_name: str
    is_active: bool
    follower_count: int
    followed_at: datetime


class StoreFollowerCountResponse(BaseModel):
    store_id: UUID
    follower_count: int
    is_following: bool


def _follower_count(store_id: UUID) -> int:
    return db_session.exec(
        select(func.count()).where(StoreFollow.store_id == store_id)
    ).one()


@store_follow_apis.post("/stores/{store_id}/follow", response_model=FollowedStoreResponse)
def follow_store(store_id: UUID, user: User = Depends(_get_user)):
    store = db_session.exec(select(Store).where(Store.id == store_id)).first()
    if not store:
        raise HTTPException(status_code=404, detail="Store not found")

    existing = db_session.exec(
        select(StoreFollow).where(
            StoreFollow.user_id == user.id,
            StoreFollow.store_id == store_id,
        )
    ).first()
    if existing:
        return FollowedStoreResponse(
            store_id=store.id, store_name=store.name, is_active=store.is_active,
            follower_count=_follower_count(store_id), followed_at=existing.created_at,
        )

    follow = StoreFollow(user_id=user.id, store_id=store_id)
    db_session.add(follow)
    db_session.commit()
    db_session.refresh(follow)

    return FollowedStoreResponse(
        store_id=store.id, store_name=store.name, is_active=store.is_active,
        follower_count=_follower_count(store_id), followed_at=follow.created_at,
    )


@store_follow_apis.delete("/stores/{store_id}/follow", status_code=204)
def unfollow_store(store_id: UUID, user: User = Depends(_get_user)):
    follow = db_session.exec(
        select(StoreFollow).where(
            StoreFollow.user_id == user.id,
            StoreFollow.store_id == store_id,
        )
    ).first()
    if follow:
        db_session.delete(follow)
        db_session.commit()


@store_follow_apis.get("/stores/following", response_model=List[FollowedStoreResponse])
def list_following(user: User = Depends(_get_user)):
    follows = db_session.exec(
        select(StoreFollow)
        .where(StoreFollow.user_id == user.id)
        .order_by(StoreFollow.created_at.desc())
    ).all()

    result = []
    for f in follows:
        store = db_session.exec(select(Store).where(Store.id == f.store_id)).first()
        if store:
            result.append(FollowedStoreResponse(
                store_id=store.id, store_name=store.name, is_active=store.is_active,
                follower_count=_follower_count(store.id), followed_at=f.created_at,
            ))
    return result


@store_follow_apis.get("/stores/{store_id}/followers", response_model=StoreFollowerCountResponse)
def get_follower_count(store_id: UUID, entity: Optional[PhoneVerification] = Depends(auth_required)):
    store = db_session.exec(select(Store).where(Store.id == store_id)).first()
    if not store:
        raise HTTPException(status_code=404, detail="Store not found")

    count = _follower_count(store_id)
    is_following = False
    if entity:
        user = db_session.exec(select(User).where(User.entity_id == entity.id)).first()
        if user:
            is_following = db_session.exec(
                select(StoreFollow).where(
                    StoreFollow.user_id == user.id,
                    StoreFollow.store_id == store_id,
                )
            ).first() is not None

    return StoreFollowerCountResponse(store_id=store_id, follower_count=count, is_following=is_following)
