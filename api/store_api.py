from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from helpers.jwt import auth_required
from models.entity.phone_verification import PhoneVerification
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


def _assert_owner(store, current_user: PhoneVerification):
    if store.entity_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to modify this store",
        )


@store_apis.post("/", status_code=status.HTTP_201_CREATED)
async def create_store(
    store_data: StoreCreate,
    current_user: PhoneVerification = Depends(auth_required),
):
    store_service = StoreService()
    return store_service.create_store(entity_id=current_user.id, **store_data.dict())


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


@store_apis.get("/{store_id}")
async def get_store(
    store_id: UUID,
    current_user: PhoneVerification = Depends(auth_required),
):
    store_service = StoreService()
    return store_service.get_store(store_id)


@store_apis.put("/{store_id}")
async def update_store(
    store_id: UUID,
    store_data: StoreUpdate,
    current_user: PhoneVerification = Depends(auth_required),
):
    store_service = StoreService()
    _assert_owner(store_service.get_store(store_id), current_user)
    return store_service.update_store(store_id, **store_data.dict(exclude_unset=True))


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
