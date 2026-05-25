import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import select

from helpers.jwt import auth_required
from api.validators.order_validation import Order, OrderHistoryItem, OrderHistoryResponse
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


def _serialize(obj):
    """Recursively convert UUIDs and datetimes to JSON-safe types."""
    if isinstance(obj, uuid.UUID):
        return str(obj)
    if isinstance(obj, list):
        return [_serialize(item) for item in obj]
    if isinstance(obj, dict):
        return {k: _serialize(v) for k, v in obj.items()}
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    return obj


@order_apis.get("/history", response_model=OrderHistoryResponse)
async def get_order_history(
    current_user: User = Depends(_get_user_profile),
):
    order_service = OrderService()
    orders = order_service.get_orders_by_user(current_user.id)
    return OrderHistoryResponse(
        orders=[
            OrderHistoryItem(
                id=o.id,
                total_price=o.total_price,
                status=o.status,
                items=o.items or [],
                order_date=o.order_date,
            )
            for o in orders
        ]
    )


@order_apis.post("/create-order", response_model=Order)
async def create_order(
    order: Order,
    current_user: User = Depends(_get_user_profile),
):
    logger.info(f"Creating order for user {current_user.id}")

    order_service = OrderService()
    order_entity = order_service.create_order(order, current_user)

    # Build the message payload using the DB-assigned id as order_id.
    order_dict = _serialize(order.dict())
    order_dict["order_id"]  = str(order_entity.id)
    order_dict["user_id"]   = str(current_user.id)
    order_dict["order_date"] = order.order_date.isoformat()

    try:
        publisher.publish_message(
            queue_name="order_queue",
            routing_key="order_queue",
            event="order_created",
            **order_dict,
        )
    except Exception:
        # Order is already persisted in PostgreSQL; a publish failure is
        # logged by the publisher.  We warn here so it appears in request
        # logs but do not fail the HTTP response.
        logger.warning(
            "order_id=%s was saved but could not be published to RabbitMQ",
            order_entity.id,
        )

    return order
