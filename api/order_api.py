import logging

from fastapi import APIRouter, Depends

from helpers.jwt import auth_required
from api.validators.order_validation import Order
from engine import publisher
from models.entity.user_entity import User
from models.service.orders_service import OrderService

logger = logging.getLogger(__name__)
order_apis = APIRouter(prefix="/order", tags=["order"])


@order_apis.post("/create-order", response_model=Order)
async def create_order(order: Order, current_user: User = Depends(auth_required)):
    logger.info(f"Creating order for user {current_user.id}")
    # import pdb; pdb.set_trace()
    # order_service = OrderService()
    # order_service.create_order(order, current_user)
    import pdb

    pdb.set_trace()
    return publisher.publish_message(
        queue_name="order_queue",
        routing_key="order_queue",
        event="order_created",
        order="Order placed",
    )
    # return order
