import logging
import uuid

from fastapi import APIRouter, Depends

from helpers.jwt import auth_required
from api.validators.order_validation import Order
from engine import publisher
from models.entity.user_entity import User
from models.service.orders_service import OrderService

logger = logging.getLogger(__name__)
order_apis = APIRouter(prefix="/order", tags=["order"])


def serialize_for_json(obj):
    """Recursively serialize objects for JSON"""
    if isinstance(obj, uuid.UUID):
        return str(obj)
    elif isinstance(obj, list):
        return [serialize_for_json(item) for item in obj]
    elif isinstance(obj, dict):
        return {key: serialize_for_json(value) for key, value in obj.items()}
    elif hasattr(obj, "isoformat"):  # datetime objects
        return obj.isoformat()
    else:
        return obj


@order_apis.post("/create-order", response_model=Order)
async def create_order(order: Order, current_user: User = Depends(auth_required)):
    logger.info(f"Creating order for user {current_user.id}")

    order_service = OrderService()
    order_service.create_order(order, current_user)

    order_dict = serialize_for_json(order.dict())
    order_dict["user_id"] = str(current_user.id)
    order_dict["order_date"] = order.order_date.isoformat()
    logger.info(f"Order dict: {order_dict}")

    publisher.publish_message(
        queue_name="order_queue",
        routing_key="order_queue",
        event="order_created",
        **order_dict,
    )
    return order
