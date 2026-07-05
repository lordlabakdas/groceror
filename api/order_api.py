# api/order_api.py
import logging
import uuid
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import select

from helpers.jwt import auth_required
from api.validators.order_validation import (
    CreateOrderRequest,
    OrderCreatedResponse,
    OrderHistoryItem,
    OrderHistoryLineItem,
    OrderHistoryResponse,
    StoreOrderItem,
    StoreOrderLineItem,
    StoreOrdersResponse,
    UpdateOrderStatusPayload,
    UpdateOrderStatusResponse,
    VALID_STATUSES,
)
from engine import publisher
from models.db import db_session
from models.entity.inventory_entity import Inventory
from models.entity.order_item_entity import OrderItem
from models.entity.phone_verification import PhoneVerification
from models.entity.store_entity import Store
from models.entity.user_entity import User
from models.service.orders_service import OrderService

logger = logging.getLogger(__name__)
order_apis = APIRouter(prefix="/order", tags=["order"])


def _get_store_profile(entity: PhoneVerification = Depends(auth_required)) -> Store:
    if entity.entity_type != "store":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Store access only")
    store = db_session.exec(select(Store).where(Store.entity_id == entity.id)).first()
    if not store:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Store profile not set. Call /user/set-profile first.",
        )
    return store


def _get_user_profile(entity: PhoneVerification = Depends(auth_required)) -> User:
    user = db_session.exec(select(User).where(User.entity_id == entity.id)).first()
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
async def get_order_history(current_user: User = Depends(_get_user_profile)):
    orders = OrderService().get_orders_by_user(current_user.id)

    if not orders:
        return OrderHistoryResponse(orders=[])

    order_ids = [o.id for o in orders]
    rows = db_session.exec(
        select(OrderItem, Inventory)
        .join(Inventory, OrderItem.inventory_id == Inventory.id)
        .where(OrderItem.order_id.in_(order_ids))
    ).all()

    items_by_order: dict = defaultdict(list)
    for oi, inv in rows:
        items_by_order[oi.order_id].append(
            OrderHistoryLineItem(
                inventory_id=oi.inventory_id,
                name=inv.name,
                quantity=oi.quantity,
                price=oi.price,
            )
        )

    store_ids = list({o.store_id for o in orders if o.store_id})
    store_name_map: dict = {}
    if store_ids:
        stores = db_session.exec(select(Store).where(Store.id.in_(store_ids))).all()
        store_name_map = {s.id: s.name for s in stores}

    return OrderHistoryResponse(
        orders=[
            OrderHistoryItem(
                id=o.id,
                total_price=o.total_price,
                discount_amount=o.discount_amount,
                points_redeemed=o.points_redeemed,
                coupon_code=o.coupon_code,
                status=o.status,
                items=items_by_order[o.id],
                order_date=o.order_date,
                store_id=o.store_id,
                store_name=store_name_map.get(o.store_id) if o.store_id else None,
            )
            for o in orders
        ]
    )


@order_apis.post("/create-order", response_model=OrderCreatedResponse)
async def create_order(
    order: CreateOrderRequest,
    current_user: User = Depends(_get_user_profile),
):
    logger.info("Creating order for user %s", current_user.id)
    try:
        order_entity, points_earned = OrderService().create_order(order, current_user)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    order_dict = _serialize(order.model_dump())
    order_dict["order_id"] = str(order_entity.id)
    order_dict["user_id"] = str(current_user.id)
    order_dict["order_date"] = order.order_date.isoformat()
    order_dict["total_price"] = order_entity.total_price
    order_dict["status"] = order_entity.status

    try:
        publisher.publish_message(
            queue_name="order_queue",
            routing_key="order_queue",
            event="order_created",
            **order_dict,
        )
    except Exception:
        logger.warning("order_id=%s was saved but could not be published", order_entity.id)

    try:
        publisher.publish_message(
            queue_name=publisher.EMAIL_QUEUE,
            routing_key=publisher.EMAIL_QUEUE,
            event="send_email",
            recipient=current_user.email,
            subject=f"Order #{order_entity.id} confirmed",
            body=(
                f"Hi {current_user.name},\n\n"
                f"Your order #{order_entity.id} has been placed successfully.\n"
                f"Total: ${order_entity.total_price:.2f}"
                + (f" (saved ${order_entity.discount_amount:.2f})" if order_entity.discount_amount else "")
                + (f"\nYou earned {points_earned} loyalty points!" if points_earned else "")
                + "\n\nThank you for shopping with Groceror!"
            ),
        )
    except Exception:
        logger.warning("order_id=%s email notification could not be published", order_entity.id)

    return OrderCreatedResponse(
        id=order_entity.id,
        status=order_entity.status,
        total_price=order_entity.total_price,
        discount_amount=order_entity.discount_amount,
        points_earned=points_earned,
    )


@order_apis.get("/store-orders", response_model=StoreOrdersResponse)
async def get_store_orders(current_store: Store = Depends(_get_store_profile)):
    orders = OrderService().get_orders_by_store(current_store.id)

    if not orders:
        return StoreOrdersResponse(orders=[])

    order_ids = [o.id for o in orders]
    rows = db_session.exec(
        select(OrderItem, Inventory)
        .join(Inventory, OrderItem.inventory_id == Inventory.id)
        .where(OrderItem.order_id.in_(order_ids))
    ).all()

    items_by_order: dict = defaultdict(list)
    for oi, inv in rows:
        items_by_order[oi.order_id].append(
            StoreOrderLineItem(
                inventory_id=oi.inventory_id,
                name=inv.name,
                quantity=oi.quantity,
                price=oi.price,
            )
        )

    return StoreOrdersResponse(
        orders=[
            StoreOrderItem(
                id=o.id,
                total_price=o.total_price,
                status=o.status,
                items=items_by_order[o.id],
                order_date=o.order_date,
            )
            for o in orders
        ]
    )


@order_apis.put("/{order_id}/status", response_model=UpdateOrderStatusResponse)
async def update_order_status(
    order_id: uuid.UUID,
    payload: UpdateOrderStatusPayload,
    current_store: Store = Depends(_get_store_profile),
):
    if payload.status not in VALID_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid status. Must be one of: {', '.join(sorted(VALID_STATUSES))}",
        )
    updated = OrderService().update_order_status(order_id, current_store.id, payload.status)
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    try:
        publisher.publish_message(
            queue_name="order_queue",
            routing_key="order_queue",
            event="order_status_updated",
            order_id=str(order_id),
            store_id=str(current_store.id),
            status=payload.status,
        )
    except Exception:
        logger.warning("order_id=%s status updated but could not be published", order_id)
    return UpdateOrderStatusResponse(message="Status updated", status=updated.status)
