import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import select

from helpers.jwt import auth_required
from api.validators.order_validation import Order
from engine import publisher
from models.db import db_session
from models.entity.phone_verification import PhoneVerification
from models.entity.user_entity import User
from models.service.orders_service import OrderService

logger = logging.getLogger(__name__)
order_apis = APIRouter(prefix="/order", tags=["order"])


def _get_user_profile(entity: PhoneVerification = Depends(auth_required)) -> User:
    """Resolve the User profile for the authenticated entity."""
    user = db_session.exec(
        select(User).where(User.entity_id == entity.id)
    ).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User profile not set. Call /user/set-profile first.",
        )
    return user


def serialize_for_json(obj):
    """Recursively serialize objects for JSON."""
    if isinstance(obj, uuid.UUID):
        return str(obj)
    elif isinstance(obj, list):
        return [serialize_for_json(item) for item in obj]
    elif isinstance(obj, dict):
        return {key: serialize_for_json(value) for key, value in obj.items()}
    elif hasattr(obj, "isoformat"):
        return obj.isoformat()
    return obj


@order_apis.post("/create-order", response_model=Order)
async def create_order(
    order: Order,
    current_user: User = Depends(_get_user_profile),
):
    logger.info(f"Creating order for user {current_user.id}")

    order_service = OrderService()
    order_service.create_order(order, current_user)

    order_dict = serialize_for_json(order.dict())
    order_dict["user_id"] = str(current_user.id)
    order_dict["order_date"] = order.order_date.isoformat()

    publisher.publish_message(
        queue_name="order_queue",
        routing_key="order_queue",
        event="order_created",
        **order_dict,
    )
    return order
