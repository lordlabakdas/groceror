import logging

from fastapi import Depends, FastAPI, HTTPException, status

from api.helpers.inventory_helper import InventoryHelper
from api.validators.inventory_validation import (AddInventoryPayload,
                                                 AddInventoryResponse)
from helpers.jwt import auth_required
from models.entity.user_entity import User

logger = logging.getLogger("groceror")
inventory_apis = FastAPI()


@inventory_apis.post("/add-inventory", response_model=AddInventoryResponse)
async def add_inventory(
    add_inventory_payload: AddInventoryPayload, user: User = Depends(auth_required)
):
    logger.info(f"Adding inventory for user: {add_inventory_payload}")
    try:
        inventory_helper_obj = InventoryHelper()
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
