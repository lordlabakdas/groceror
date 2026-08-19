# api/webhook_api.py
"""Inbound webhooks from delivery vendors.

UNVERIFIED: the signature header name and HMAC scheme below are a
best-effort guess (HMAC-SHA256 over the raw body, hex digest, in an
`X-Shiprocket-Signature` header) — Shiprocket Quick's real webhook auth
mechanism wasn't available during vendor evaluation (see
GROCEROR_CONTEXT.md §10, SPEC_DELIVERY_DISPATCH.md §3.1). Confirm and
adjust once real docs/credentials are in hand.
"""

import hashlib
import hmac
import logging

from fastapi import APIRouter, HTTPException, Request, status
from sqlmodel import select

from api.sse_bus import publish as sse_publish
from config import ShiprocketConfig
from models.db import db_session
from models.entity.orders_entity import Order as OrderEntity
from models.service.delivery_service import DeliveryService

logger = logging.getLogger(__name__)
webhook_apis = APIRouter(prefix="/webhooks", tags=["webhooks"])


def _verify_shiprocket_signature(raw_body: bytes, signature: str | None) -> bool:
    if not signature or not ShiprocketConfig.WEBHOOK_SECRET:
        return False
    expected = hmac.new(
        ShiprocketConfig.WEBHOOK_SECRET.encode(), raw_body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


@webhook_apis.post("/shiprocket-quick")
async def shiprocket_quick_webhook(request: Request):
    raw_body = await request.body()
    signature = request.headers.get("X-Shiprocket-Signature")

    if not _verify_shiprocket_signature(raw_body, signature):
        logger.warning("Rejected unverified Shiprocket Quick webhook request")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid signature"
        )

    payload = await request.json()
    vendor_delivery_id = payload.get("vendor_delivery_id")
    new_status = payload.get("status")
    if not vendor_delivery_id or not new_status:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Malformed webhook payload"
        )

    delivery = DeliveryService().apply_webhook_update(
        vendor_delivery_id=vendor_delivery_id,
        status=new_status,
        rider_name=payload.get("rider_name"),
        rider_phone=payload.get("rider_phone"),
        tracking_url=payload.get("tracking_url"),
        raw_payload=raw_body.decode(errors="replace"),
    )
    if not delivery:
        # Not actionable -- e.g. an update for a delivery we don't have a
        # record of. Ack with 200 anyway so the vendor doesn't retry forever.
        logger.warning("Webhook for unknown vendor_delivery_id=%s", vendor_delivery_id)
        return {"received": True}

    order_row = db_session.exec(
        select(OrderEntity).where(OrderEntity.id == delivery.order_id)
    ).first()
    if order_row and order_row.user_id:
        sse_publish(
            str(order_row.user_id),
            "delivery_status_update",
            {"order_id": str(delivery.order_id), "status": delivery.status},
        )

    return {"received": True}
