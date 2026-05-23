from unittest.mock import MagicMock

from engine.publisher import _declare_topology


def test_user_events_dlq_declared():
    ch = MagicMock()
    _declare_topology(ch)
    queue_calls = {
        call.kwargs["queue"]: call.kwargs
        for call in ch.queue_declare.call_args_list
    }
    assert "user_events_queue.dlq" in queue_calls
    assert queue_calls["user_events_queue.dlq"].get("durable") is True


def test_user_events_dlq_bound_to_dlx():
    ch = MagicMock()
    _declare_topology(ch)
    bind_calls = {
        call.kwargs["queue"]: call.kwargs
        for call in ch.queue_bind.call_args_list
    }
    assert "user_events_queue.dlq" in bind_calls
    assert bind_calls["user_events_queue.dlq"]["exchange"] == "dlx"
    assert bind_calls["user_events_queue.dlq"]["routing_key"] == "user_events_queue"
