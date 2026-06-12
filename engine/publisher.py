"""
SQS publisher for groceror.

Replaces the pika/RabbitMQ publisher with boto3/SQS so the API can run
inside ECS while companion services consume events as Lambda functions.

Queue URLs are read from environment variables at module import time:
  USER_EVENTS_QUEUE_URL  — for user_events_queue
  EMAIL_QUEUE_URL        — for email_queue
  ORDER_QUEUE_URL        — for order_queue

When a URL is missing the publish is skipped with a warning, so the app
remains functional in local dev without AWS credentials.
"""

import json
import logging
import os
from typing import Any

import boto3

logger = logging.getLogger(__name__)

SCHEMA_VERSION = "2.0"
USER_EVENTS_QUEUE = "user_events_queue"
EMAIL_QUEUE = "email_queue"
ORDER_QUEUE = "order_queue"

_QUEUE_URL_MAP: dict[str, str] = {
    USER_EVENTS_QUEUE: os.environ.get("USER_EVENTS_QUEUE_URL", ""),
    EMAIL_QUEUE: os.environ.get("EMAIL_QUEUE_URL", ""),
    ORDER_QUEUE: os.environ.get("ORDER_QUEUE_URL", ""),
}

_sqs = None


def _get_client():
    global _sqs
    if _sqs is None:
        _sqs = boto3.client("sqs", region_name=os.environ.get("AWS_REGION", "us-east-1"))
    return _sqs


def publish_message(event: str, routing_key: str, queue_name: str, **kwargs: Any) -> None:
    """Publish a JSON message to the SQS queue mapped to *queue_name*.

    Adds ``event`` and ``schema_version`` to the envelope alongside any extra
    keyword arguments supplied by the caller.  The ``routing_key`` parameter is
    accepted for API compatibility with the former RabbitMQ publisher but is
    unused — SQS queues are addressed by URL.
    """
    url = _QUEUE_URL_MAP.get(queue_name)
    if not url:
        logger.warning(
            "No SQS URL configured for queue=%s (set %s_URL env var) — skipping publish",
            queue_name,
            queue_name.upper(),
        )
        return

    message: dict = {
        "schema_version": SCHEMA_VERSION,
        "event": event,
        **kwargs,
    }

    try:
        _get_client().send_message(
            QueueUrl=url,
            MessageBody=json.dumps(message),
        )
        logger.info(
            "Published event=%s to queue=%s order_id=%s",
            event,
            queue_name,
            kwargs.get("order_id", "n/a"),
        )
    except Exception as exc:
        logger.error("Failed to publish event=%s to queue=%s: %s", event, queue_name, exc)
        raise
