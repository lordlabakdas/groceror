"""
Server-Sent Events streaming endpoint.

Browser EventSource does not support custom headers, so the JWT is accepted
as a ?token= query parameter here (SSE-only exception to the usual Bearer pattern).
"""
import asyncio
import json
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlmodel import select

from api.sse_bus import subscribe, unsubscribe
from helpers.jwt import JWT
from models.db import db_session
from models.entity.store_entity import Store
from models.entity.user_entity import User

logger = logging.getLogger(__name__)
sse_apis = APIRouter(prefix="/sse", tags=["sse"])

KEEPALIVE_INTERVAL = 25  # seconds


def _resolve_channel(token: str) -> Optional[str]:
    """Decode token → PhoneVerification → User or Store UUID string."""
    try:
        decoded = JWT().decode_token(token)
        phone = decoded.get("sub")
        if not phone:
            return None
    except Exception:
        return None

    from api.helpers.auth_helper import get_user_by_phone
    entity = get_user_by_phone(phone=phone)
    if not entity:
        return None

    store = db_session.exec(select(Store).where(Store.entity_id == entity.id)).first()
    if store:
        return str(store.id)

    user = db_session.exec(select(User).where(User.entity_id == entity.id)).first()
    if user:
        return str(user.id)

    return None


async def _event_stream(channel_id: str, q: asyncio.Queue):
    try:
        while True:
            try:
                msg = await asyncio.wait_for(q.get(), timeout=KEEPALIVE_INTERVAL)
                payload = f"event: {msg['event']}\ndata: {json.dumps(msg['data'])}\n\n"
                yield payload
            except asyncio.TimeoutError:
                # keepalive comment — prevents proxies / browsers from closing the connection
                yield ": keepalive\n\n"
    except asyncio.CancelledError:
        pass
    finally:
        unsubscribe(channel_id, q)
        logger.debug("SSE client disconnected: channel=%s", channel_id)


@sse_apis.get("/stream")
async def sse_stream(token: str = Query(...)):
    channel_id = _resolve_channel(token)
    if channel_id is None:
        raise HTTPException(status_code=401, detail="Invalid or missing token")

    q = subscribe(channel_id)
    logger.debug("SSE client connected: channel=%s", channel_id)

    return StreamingResponse(
        _event_stream(channel_id, q),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # disable nginx buffering
        },
    )
