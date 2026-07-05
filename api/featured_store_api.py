from datetime import date, datetime
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlmodel import select

from helpers.jwt import auth_required
from models.db import db_session
from models.entity.featured_store_entity import FeaturedStore
from models.entity.phone_verification import PhoneVerification
from models.entity.store_entity import Store

featured_store_apis = APIRouter(tags=["featured-stores"])


def _get_store(entity: PhoneVerification = Depends(auth_required)) -> Store:
    if entity.entity_type != "store":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Store access only")
    store = db_session.exec(select(Store).where(Store.entity_id == entity.id)).first()
    if not store:
        raise HTTPException(status_code=400, detail="Store profile not set")
    return store


class SetFeaturedPayload(BaseModel):
    tagline: Optional[str] = None
    priority: int = 0
    start_date: Optional[date] = None
    end_date: Optional[date] = None


class FeaturedStoreResponse(BaseModel):
    store_id: UUID
    store_name: str
    tagline: Optional[str]
    priority: int
    start_date: Optional[date]
    end_date: Optional[date]
    is_active: bool


def _is_currently_active(fs: FeaturedStore) -> bool:
    today = date.today()
    if not fs.is_active:
        return False
    if fs.start_date and today < fs.start_date:
        return False
    if fs.end_date and today > fs.end_date:
        return False
    return True


@featured_store_apis.put("/stores/feature", response_model=FeaturedStoreResponse)
def set_featured(payload: SetFeaturedPayload, store: Store = Depends(_get_store)):
    existing = db_session.exec(
        select(FeaturedStore).where(FeaturedStore.store_id == store.id)
    ).first()

    if existing:
        existing.tagline = payload.tagline
        existing.priority = payload.priority
        existing.start_date = payload.start_date
        existing.end_date = payload.end_date
        existing.is_active = True
        existing.updated_at = datetime.utcnow()
        db_session.commit()
        db_session.refresh(existing)
        fs = existing
    else:
        fs = FeaturedStore(
            store_id=store.id,
            tagline=payload.tagline,
            priority=payload.priority,
            start_date=payload.start_date,
            end_date=payload.end_date,
        )
        db_session.add(fs)
        db_session.commit()
        db_session.refresh(fs)

    return FeaturedStoreResponse(
        store_id=store.id,
        store_name=store.name,
        tagline=fs.tagline,
        priority=fs.priority,
        start_date=fs.start_date,
        end_date=fs.end_date,
        is_active=fs.is_active,
    )


@featured_store_apis.delete("/stores/feature", status_code=204)
def remove_featured(store: Store = Depends(_get_store)):
    existing = db_session.exec(
        select(FeaturedStore).where(FeaturedStore.store_id == store.id)
    ).first()
    if existing:
        existing.is_active = False
        existing.updated_at = datetime.utcnow()
        db_session.commit()


@featured_store_apis.get("/stores/feature/me", response_model=Optional[FeaturedStoreResponse])
def get_my_featured(store: Store = Depends(_get_store)):
    fs = db_session.exec(
        select(FeaturedStore).where(FeaturedStore.store_id == store.id)
    ).first()
    if not fs:
        return None
    return FeaturedStoreResponse(
        store_id=store.id,
        store_name=store.name,
        tagline=fs.tagline,
        priority=fs.priority,
        start_date=fs.start_date,
        end_date=fs.end_date,
        is_active=fs.is_active,
    )


@featured_store_apis.get("/stores/featured", response_model=List[FeaturedStoreResponse])
def list_featured_stores():
    rows = db_session.exec(
        select(FeaturedStore, Store)
        .join(Store, FeaturedStore.store_id == Store.id)
        .order_by(FeaturedStore.priority.desc())
    ).all()

    result = []
    for fs, store in rows:
        if not _is_currently_active(fs):
            continue
        result.append(
            FeaturedStoreResponse(
                store_id=store.id,
                store_name=store.name,
                tagline=fs.tagline,
                priority=fs.priority,
                start_date=fs.start_date,
                end_date=fs.end_date,
                is_active=fs.is_active,
            )
        )
    return result
