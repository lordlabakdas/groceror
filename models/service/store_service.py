from datetime import datetime
from typing import List, Optional, Tuple
from uuid import UUID

import requests
from fastapi import HTTPException, status
from sqlalchemy import text

from models.db import db_session
from models.entity.store_entity import Store
from models.entity.user_entity import User


def get_coordinates(address: str) -> Tuple[float, float]:
    # Use Google Maps API to get coordinates
    url = f"https://maps.googleapis.com/maps/api/geocode/json?address={address}&key={os.getenv('GOOGLE_MAPS_API_KEY')}"
    try:
        response = requests.get(url)
        data = response.json()
        return (
            data["results"][0]["geometry"]["location"]["lat"],
            data["results"][0]["geometry"]["location"]["lng"],
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting coordinates: {str(e)}",
        )


class StoreService:
    def create_store(
        self,
        name: str,
        user_id: UUID,
        address: str,
        phone: str,
        email: str,
        website: str = None,
    ) -> Store:
        try:
            latitude, longitude = get_coordinates(address)
            store = Store(
                name=name,
                user_id=user_id,
                address=address,
                phone=phone,
                email=email,
                website=website,
                latitude=latitude,
                longitude=longitude,
            )
            db_session.add(store)
            db_session.commit()
            db_session.refresh(store)
            return store
        except Exception as e:
            db_session.rollback()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to create store: {str(e)}",
            )

    def get_store(self, store_id: UUID) -> Optional[Store]:
        store = db_session.query(Store).filter(Store.id == store_id).first()
        if not store:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Store with id {store_id} not found",
            )
        return store

    def get_stores_by_user(self, user_id: UUID) -> List[Store]:
        return db_session.query(Store).filter(Store.user_id == user_id).all()

    def get_store_by_email(self, email: str) -> Optional[Store]:
        return db_session.query(Store).filter(Store.email == email).first()

    def update_store(self, store_id: UUID, **update_data) -> Store:
        try:
            store = self.get_store(store_id)
            for key, value in update_data.items():
                if hasattr(store, key):
                    setattr(store, key, value)
            store.updated_at = datetime.utcnow()
            db_session.commit()
            db_session.refresh(store)
            return store
        except Exception as e:
            db_session.rollback()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to update store: {str(e)}",
            )

    def delete_store(self, store_id: UUID) -> bool:
        try:
            store = self.get_store(store_id)
            db_session.delete(store)
            db_session.commit()
            return True
        except Exception as e:
            db_session.rollback()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to delete store: {str(e)}",
            )

    def deactivate_store(self, store_id: UUID) -> Store:
        return self.update_store(store_id, is_active=False)

    def activate_store(self, store_id: UUID) -> Store:
        return self.update_store(store_id, is_active=True)

    def search_stores(self, query: str) -> List[Store]:
        return (
            db_session.query(Store)
            .filter(
                (Store.name.ilike(f"%{query}%"))
                | (Store.email.ilike(f"%{query}%"))
                | (Store.phone.ilike(f"%{query}%"))
                | (Store.address.ilike(f"%{query}%"))
            )
            .all()
        )

    def find_nearby_stores(
        self, latitude: float, longitude: float, radius: float = 10.0
    ) -> List[dict]:
        """
        Find stores within specified radius (in kilometers) using Haversine formula
        """
        try:
            # SQL query using Haversine formula
            query = text(
                """
                SELECT 
                    id,
                    name,
                    address,
                    latitude,
                    longitude,
                    phone,
                    email,
                    website,
                    ( 6371 * acos( cos( radians(:lat) ) * 
                        cos( radians( latitude ) ) * 
                        cos( radians( longitude ) - radians(:lon) ) + 
                        sin( radians(:lat) ) * 
                        sin( radians( latitude ) ) 
                    )) AS distance 
                FROM store 
                WHERE is_active = true
                HAVING distance <= :radius 
                ORDER BY distance;
            """
            )

            result = db_session.execute(
                query, {"lat": latitude, "lon": longitude, "radius": radius}
            )

            stores = []
            for row in result:
                store_dict = {
                    "id": row.id,
                    "name": row.name,
                    "address": row.address,
                    "latitude": row.latitude,
                    "longitude": row.longitude,
                    "distance": round(row.distance, 2),  # Round to 2 decimal places
                    "phone": row.phone,
                    "email": row.email,
                    "website": row.website,
                }
                stores.append(store_dict)

            return stores

        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error finding nearby stores: {str(e)}",
            )
