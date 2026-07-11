"""
In-process event bus for Server-Sent Events.

Synchronous callers (FastAPI sync route handlers running in the thread pool)
use `publish()`, which is thread-safe via loop.call_soon_threadsafe.

The SSE streaming endpoint (async) reads from per-subscriber asyncio.Queue
instances registered here.
"""
import asyncio
from collections import defaultdict
from typing import Dict, List

# channel_id (str of UUID) → list of open subscriber queues
_subscribers: Dict[str, List[asyncio.Queue]] = defaultdict(list)
_loop: asyncio.AbstractEventLoop | None = None


def set_loop(loop: asyncio.AbstractEventLoop) -> None:
    global _loop
    _loop = loop


def subscribe(channel_id: str) -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue()
    _subscribers[channel_id].append(q)
    return q


def unsubscribe(channel_id: str, q: asyncio.Queue) -> None:
    try:
        _subscribers[channel_id].remove(q)
    except ValueError:
        pass


def publish(channel_id: str, event_type: str, data: dict) -> None:
    """Thread-safe: safe to call from sync route handlers."""
    if _loop is None or not _loop.is_running():
        return
    msg = {"event": event_type, "data": data}
    for q in list(_subscribers.get(channel_id, [])):
        _loop.call_soon_threadsafe(q.put_nowait, msg)
