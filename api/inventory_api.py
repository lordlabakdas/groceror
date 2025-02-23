import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status

from api.helpers.inventory_helper import InventoryHelper
from api.validators.inventory_validation import (
    AddInventoryPayload,
    AddInventoryResponse,
    StoreInventoryResponse,
)
from helpers.jwt import auth_required
from models.entity.user_entity import User

logger = logging.getLogger("groceror")
inventory_apis = APIRouter(prefix="/inventory", tags=["inventory"])


@inventory_apis.post("/add-inventory", response_model=AddInventoryResponse)
async def add_inventory(
    add_inventory_payload: AddInventoryPayload, user: User = Depends(auth_required)
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
    items: List[str] = None,
    user: User = Depends(auth_required),
):
    logger.info(f"Getting inventory for store: {user.email}")
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


@inventory_apis.delete("/delete-inventory", response_model=StoreInventoryResponse)
async def delete_inventory(
    items: List[str] = None,
    user: User = Depends(auth_required),
):
    logger.info(f"Deleting inventory for user: {user.email}")
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
