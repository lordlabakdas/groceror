import logging
from datetime import datetime
from math import asin, cos, radians, sin, sqrt
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field as PydanticField
from sqlmodel import select

from helpers.jwt import auth_required
from models.db import db_session
from models.entity.delivery_zone_entity import DeliveryZone
from models.entity.phone_verification import PhoneVerification
from models.entity.store_entity import Store

logger = logging.getLogger(__name__)
delivery_zone_apis = APIRouter(prefix="/delivery-zones", tags=["delivery-zones"])

EARTH_RADIUS_KM = 6371.0


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in km between two (lat, lon) points."""
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_KM * asin(sqrt(a))


def _get_store(entity: PhoneVerification = Depends(auth_required)) -> Store:
    if entity.entity_type != "store":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Store access only")
    store = db_session.exec(select(Store).where(Store.entity_id == entity.id)).first()
    if not store:
        raise HTTPException(status_code=400, detail="Store profile not set")
    return store


class SetDeliveryZonePayload(BaseModel):
    latitude: float = PydanticField(..., ge=-90, le=90)
    longitude: float = PydanticField(..., ge=-180, le=180)
    radius_km: float = PydanticField(..., gt=0)


class DeliveryZoneResponse(BaseModel):
    id: UUID
    store_id: UUID
    latitude: float
    longitude: float
    radius_km: float


class NearbyStoreResponse(BaseModel):
    store_id: UUID
    store_name: str
    distance_km: float
    latitude: float
    longitude: float
    radius_km: float


@delivery_zone_apis.put("", response_model=DeliveryZoneResponse)
async def set_delivery_zone(payload: SetDeliveryZonePayload, store: Store = Depends(_get_store)):
    zone = db_session.exec(
        select(DeliveryZone).where(DeliveryZone.store_id == store.id)
    ).first()
    if zone:
        zone.latitude = payload.latitude
        zone.longitude = payload.longitude
        zone.radius_km = payload.radius_km
        zone.updated_at = datetime.utcnow()
    else:
        zone = DeliveryZone(
            store_id=store.id,
            latitude=payload.latitude,
            longitude=payload.longitude,
            radius_km=payload.radius_km,
        )
        db_session.add(zone)
    db_session.commit()
    db_session.refresh(zone)
    return zone


@delivery_zone_apis.get("/store/{store_id}", response_model=Optional[DeliveryZoneResponse])
async def get_store_delivery_zone(store_id: UUID):
    zone = db_session.exec(
        select(DeliveryZone).where(DeliveryZone.store_id == store_id)
    ).first()
    return zone


@delivery_zone_apis.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def remove_delivery_zone(store: Store = Depends(_get_store)):
    zone = db_session.exec(
        select(DeliveryZone).where(DeliveryZone.store_id == store.id)
    ).first()
    if not zone:
        raise HTTPException(status_code=404, detail="No delivery zone configured")
    db_session.delete(zone)
    db_session.commit()


@delivery_zone_apis.get("/nearby", response_model=List[NearbyStoreResponse])
async def get_nearby_stores(lat: float, lng: float):
    """Return stores whose delivery zone covers (lat, lng)."""
    zones = db_session.exec(select(DeliveryZone)).all()
    store_ids = [z.store_id for z in zones]
    stores = db_session.exec(select(Store).where(Store.id.in_(store_ids))).all()
    store_map = {s.id: s for s in stores}

    nearby: List[NearbyStoreResponse] = []
    for zone in zones:
        dist = _haversine(lat, lng, zone.latitude, zone.longitude)
        if dist <= zone.radius_km:
            s = store_map.get(zone.store_id)
            if s:
                nearby.append(NearbyStoreResponse(
                    store_id=zone.store_id,
                    store_name=s.name,
                    distance_km=round(dist, 2),
                    latitude=zone.latitude,
                    longitude=zone.longitude,
                    radius_km=zone.radius_km,
                ))
    nearby.sort(key=lambda x: x.distance_km)
    return nearby
