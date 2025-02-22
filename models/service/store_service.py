from typing import List, Optional
from uuid import UUID
from datetime import datetime
from fastapi import HTTPException, status

from models.db import db_session
from models.entity.store_entity import Store
from models.entity.user_entity import User


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
            store = Store(
                name=name,
                user_id=user_id,
                address=address,
                phone=phone,
                email=email,
                website=website,
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
