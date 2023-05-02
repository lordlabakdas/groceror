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
inventory_apis = APIRouter()

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

@inventory_apis.post("/get-store-inventory", response_model=StoreInventoryResponse)
async def get_store_inventory(
    items: List[str] = None,
    quantity_limit: int = None,
    user: User = Depends(auth_required),
):
    logger.info(f"Getting inventory for store: {user.email}")
    try:
        inventory_helper_obj = InventoryHelper(user=user)
        inventory = inventory_helper_obj.get_store_inventory(
            items=items, quantity_limit=quantity_limit
        )
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
