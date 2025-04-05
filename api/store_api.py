from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel

from helpers.jwt import auth_required
from models.entity.user_entity import User
from models.service.store_service import StoreService

store_apis = APIRouter(prefix="/stores", tags=["stores"])


class StoreCreate(BaseModel):
    name: str
    address: str
    latitude: float
    longitude: float
    phone: str
    email: str
    website: str = None


class StoreUpdate(BaseModel):
    name: str = None
    address: str = None
    phone: str = None
    email: str = None
    website: str = None


class Location(BaseModel):
    latitude: float
    longitude: float
    radius: Optional[float] = 10.0  # Default 10km radius


class StoreWithDistance(BaseModel):
    id: UUID
    name: str
    address: str
    latitude: float
    longitude: float
    distance: float  # Distance in kilometers
    phone: str
    email: str
    website: Optional[str]


@store_apis.post("/", status_code=status.HTTP_201_CREATED)
async def create_store(
    store_data: StoreCreate, current_user: User = Depends(auth_required)
):
    store_service = StoreService()
    return store_service.create_store(user_id=current_user.id, **store_data.dict())


@store_apis.get("/{store_id}")
async def get_store(store_id: UUID, current_user: User = Depends(auth_required)):
    store_service = StoreService()
    return store_service.get_store(store_id)


@store_apis.get("/")
async def get_user_stores(current_user: User = Depends(auth_required)):
    store_service = StoreService()
    return store_service.get_stores_by_user(current_user.id)


@store_apis.put("/{store_id}")
async def update_store(
    store_id: UUID, store_data: StoreUpdate, current_user: User = Depends(auth_required)
):
    store_service = StoreService()
    store = store_service.get_store(store_id)
    if store.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to update this store",
        )
    return store_service.update_store(store_id, **store_data.dict(exclude_unset=True))


@store_apis.delete("/{store_id}")
async def delete_store(store_id: UUID, current_user: User = Depends(auth_required)):
    store_service = StoreService()
    store = store_service.get_store(store_id)
    if store.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to delete this store",
        )
    return store_service.delete_store(store_id)


@store_apis.post("/{store_id}/deactivate")
async def deactivate_store(store_id: UUID, current_user: User = Depends(auth_required)):
    store_service = StoreService()
    store = store_service.get_store(store_id)
    if store.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to deactivate this store",
        )
    return store_service.deactivate_store(store_id)


@store_apis.post("/{store_id}/activate")
async def activate_store(store_id: UUID, current_user: User = Depends(auth_required)):
    store_service = StoreService()
    store = store_service.get_store(store_id)
    if store.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to activate this store",
        )
    return store_service.activate_store(store_id)


@store_apis.get("/search/{query}")
async def search_stores(query: str, current_user: User = Depends(auth_required)):
    store_service = StoreService()
    return store_service.search_stores(query)


@store_apis.get("/nearby/", response_model=List[StoreWithDistance])
async def get_nearby_stores(
    latitude: float = Query(..., description="Latitude of the search location"),
    longitude: float = Query(..., description="Longitude of the search location"),
    radius: float = Query(10.0, description="Search radius in kilometers"),
    current_user: User = Depends(auth_required)
):
    store_service = StoreService()
    return store_service.find_nearby_stores(latitude, longitude, radius)
