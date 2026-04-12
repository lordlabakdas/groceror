import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from api.helpers.inventory_helper import InventoryHelper
from api.validators.inventory_validation import (
    AddInventoryPayload,
    AddInventoryResponse,
    DeleteInventoryResponse,
    StoreInventoryResponse,
)
from helpers.jwt import auth_required
from models.entity.phone_verification import PhoneVerification
from models.entity.user_entity import User

logger = logging.getLogger(__name__)
inventory_apis = APIRouter(prefix="/inventory", tags=["inventory"])


@inventory_apis.post("/add-inventory", response_model=AddInventoryResponse)
async def add_inventory(
    add_inventory_payload: AddInventoryPayload, user: PhoneVerification = Depends(auth_required)
):
    logger.info(f"Adding inventory for user: {add_inventory_payload}")
    try:
        inventory_helper_obj = InventoryHelper(user=user)
        new_inventory_id = inventory_helper_obj.add_inventory(
            **add_inventory_payload.dict()
        )
    except Exception as e:
        logger.exception(f"Error while adding inventory with exception details {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Issue with registering user",
        )
    else:
        return {"inventory_id": new_inventory_id}


@inventory_apis.get("/get-store-inventory", response_model=StoreInventoryResponse)
async def get_store_inventory(
    items: Optional[List[str]] = Query(default=None),
    user: User = Depends(auth_required),
):
    logger.info(f"Getting inventory for store: {user.phone}")
    try:
        inventory_helper_obj = InventoryHelper(user=user)
        inventory = inventory_helper_obj.get_store_inventory(items=items)
    except Exception as e:
        logger.exception(
            f"Error while retreiving store inventory with exception details {e}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Issue with retreiving store inventory",
        )
    else:
        return StoreInventoryResponse(inventory=inventory)


@inventory_apis.delete("/delete-inventory", response_model=DeleteInventoryResponse)
async def delete_inventory(
    items: Optional[List[str]] = Query(default=None),
    user: User = Depends(auth_required),
):
    logger.info(f"Deleting inventory for user: {user.phone}")
    try:
        inventory_helper_obj = InventoryHelper(user=user)
        inventory_helper_obj.delete_inventory(items=items)
    except Exception as e:
        logger.exception(f"Error while deleting inventory with exception details {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Issue with deleting inventory",
        )
    else:
        return {"status": "success"}
