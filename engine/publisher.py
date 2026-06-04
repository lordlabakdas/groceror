"""
RabbitMQ publisher for groceror.

Uses one thread-local BlockingConnection per worker thread so that:
- Connections are not shared across threads (pika.BlockingConnection is not
  thread-safe).
- We avoid the per-call open/close overhead of the previous implementation.

Every published message includes a ``schema_version`` field so that consumers
can reject or handle messages from older/newer producer versions gracefully.

Dead-letter exchange (``dlx``) and dead-letter queues (``order_queue.dlq``,
``user_events_queue.dlq``, ``email_queue.dlq``) are declared on first use so
that NACKed or expired messages are never silently dropped.
"""

import json
import logging
import threading
from typing import Any

import pika

from config import RabbitMQConfig

logger = logging.getLogger(__name__)

SCHEMA_VERSION = "2.0"
DLX_EXCHANGE   = "dlx"
DLQ_NAME       = "order_queue.dlq"
USER_EVENTS_QUEUE = "user_events_queue"
USER_EVENTS_DLQ   = "user_events_queue.dlq"
EMAIL_QUEUE = "email_queue"
EMAIL_DLQ   = "email_queue.dlq"

_local = threading.local()


def _get_channel() -> pika.adapters.blocking_connection.BlockingChannel:
    """Return a ready channel for the current thread, reconnecting if needed."""
    conn: pika.BlockingConnection | None = getattr(_local, "connection", None)

    if conn is None or conn.is_closed:
        credentials = pika.PlainCredentials(RabbitMQConfig.USER, RabbitMQConfig.PASSWORD)
        parameters = pika.ConnectionParameters(
            host=RabbitMQConfig.HOST,
            port=RabbitMQConfig.PORT,
            virtual_host=RabbitMQConfig.VHOST,
            credentials=credentials,
            heartbeat=600,
            blocked_connection_timeout=300,
        )
        _local.connection = pika.BlockingConnection(parameters)
        _local.channel = None  # channel must be re-created with new connection

    channel: pika.adapters.blocking_connection.BlockingChannel | None = getattr(
        _local, "channel", None
    )
    if channel is None or channel.is_closed:
        channel = _local.connection.channel()
        _declare_topology(channel)
        _local.channel = channel

    return channel


def _declare_topology(channel: pika.adapters.blocking_connection.BlockingChannel) -> None:
    """Declare the shared DLX exchange and both service DLQs."""
    channel.exchange_declare(exchange=DLX_EXCHANGE, exchange_type="direct", durable=True)
    # order events DLQ
    channel.queue_declare(queue=DLQ_NAME, durable=True)
    channel.queue_bind(exchange=DLX_EXCHANGE, queue=DLQ_NAME, routing_key="order_queue")
    # user events DLQ
    channel.queue_declare(queue=USER_EVENTS_DLQ, durable=True)
    channel.queue_bind(exchange=DLX_EXCHANGE, queue=USER_EVENTS_DLQ, routing_key=USER_EVENTS_QUEUE)
    # email events DLQ
    channel.queue_declare(queue=EMAIL_DLQ, durable=True)
    channel.queue_bind(exchange=DLX_EXCHANGE, queue=EMAIL_DLQ, routing_key=EMAIL_QUEUE)


def _declare_queue(
    channel: pika.adapters.blocking_connection.BlockingChannel, queue_name: str
) -> None:
    """Declare a durable queue with dead-letter routing attached."""
    channel.queue_declare(
        queue=queue_name,
        durable=True,
        arguments={
            "x-dead-letter-exchange": DLX_EXCHANGE,
            "x-dead-letter-routing-key": queue_name,
        },
    )


def publish_message(event: str, routing_key: str, queue_name: str, **kwargs: Any) -> None:
    """Publish a JSON message to *queue_name*.

    Adds ``event`` and ``schema_version`` to the envelope alongside any extra
    keyword arguments supplied by the caller.

    Raises:
        Exception: Re-raises any pika/connection error after logging it so the
            caller can decide whether to surface the failure.
    """
    message: dict = {
        "schema_version": SCHEMA_VERSION,
        "event": event,
        **kwargs,
    }

    try:
        channel = _get_channel()
        _declare_queue(channel, queue_name)

        channel.basic_publish(
            exchange="",
            routing_key=routing_key,
            body=json.dumps(message),
            properties=pika.BasicProperties(
                delivery_mode=2,           # persistent
                content_type="application/json",
            ),
        )
        logger.info(
            "Published event=%s to queue=%s order_id=%s",
            event,
            queue_name,
            kwargs.get("order_id", "n/a"),
        )

    except Exception as exc:
        # Invalidate the thread-local channel/connection so the next call
        # gets a fresh one rather than retrying on a broken socket.
        _local.channel = None
        _local.connection = None
        logger.error("Failed to publish event=%s to queue=%s: %s", event, queue_name, exc)
        raise
