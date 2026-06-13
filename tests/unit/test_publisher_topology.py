"""Tests for the SQS publisher (replaces the old RabbitMQ topology tests)."""
import importlib
import json
import os
from unittest.mock import MagicMock, patch


def _reload_publisher(env: dict):
    """Reload publisher module with a custom env so _QUEUE_URL_MAP is re-evaluated."""
    import engine.publisher as mod
    with patch.dict(os.environ, env, clear=False):
        importlib.reload(mod)
    return mod


def test_publish_sends_to_correct_queue_url():
    """publish_message calls sqs.send_message with the configured queue URL."""
    import engine.publisher as mod
    fake_sqs = MagicMock()
    env = {"USER_EVENTS_QUEUE_URL": "https://sqs.us-east-1.amazonaws.com/123/user_events_queue"}
    mod_reloaded = _reload_publisher(env)
    with patch.object(mod_reloaded, "_sqs", fake_sqs):
        mod_reloaded.publish_message(
            event="USER_REGISTERED",
            routing_key=mod_reloaded.USER_EVENTS_QUEUE,
            queue_name=mod_reloaded.USER_EVENTS_QUEUE,
            user_id="abc",
        )
    fake_sqs.send_message.assert_called_once()
    call_kwargs = fake_sqs.send_message.call_args.kwargs
    assert call_kwargs["QueueUrl"] == env["USER_EVENTS_QUEUE_URL"]
    body = json.loads(call_kwargs["MessageBody"])
    assert body["event"] == "USER_REGISTERED"
    assert body["schema_version"] == "2.0"
    assert body["user_id"] == "abc"


def test_publish_skips_when_url_not_configured(caplog):
    """publish_message logs a warning and returns without raising when queue URL is absent."""
    import engine.publisher as mod
    env = {"USER_EVENTS_QUEUE_URL": ""}
    mod_reloaded = _reload_publisher(env)
    fake_sqs = MagicMock()
    with patch.object(mod_reloaded, "_sqs", fake_sqs):
        mod_reloaded.publish_message(
            event="USER_REGISTERED",
            routing_key=mod_reloaded.USER_EVENTS_QUEUE,
            queue_name=mod_reloaded.USER_EVENTS_QUEUE,
        )
    fake_sqs.send_message.assert_not_called()


def test_queue_constants_match_sqs_map():
    """Queue name constants must be keys in _QUEUE_URL_MAP so publishes are routable."""
    import engine.publisher as mod
    for constant in (mod.USER_EVENTS_QUEUE, mod.EMAIL_QUEUE, mod.ORDER_QUEUE):
        assert constant in mod._QUEUE_URL_MAP, f"{constant!r} missing from _QUEUE_URL_MAP"


def test_email_queue_url_used_for_email_publishes():
    import engine.publisher as mod
    fake_sqs = MagicMock()
    env = {"EMAIL_QUEUE_URL": "https://sqs.us-east-1.amazonaws.com/123/email_queue"}
    mod_reloaded = _reload_publisher(env)
    with patch.object(mod_reloaded, "_sqs", fake_sqs):
        mod_reloaded.publish_message(
            event="ORDER_PLACED",
            routing_key=mod_reloaded.EMAIL_QUEUE,
            queue_name=mod_reloaded.EMAIL_QUEUE,
        )
    call_kwargs = fake_sqs.send_message.call_args.kwargs
    assert call_kwargs["QueueUrl"] == env["EMAIL_QUEUE_URL"]
