from unittest.mock import MagicMock

from engine.publisher import _declare_topology


def test_user_events_dlq_declared():
    ch = MagicMock()
    _declare_topology(ch)
    queue_names = [call.kwargs.get("queue") for call in ch.queue_declare.call_args_list]
    assert "user_events_queue.dlq" in queue_names


def test_user_events_dlq_bound_to_dlx():
    ch = MagicMock()
    _declare_topology(ch)
    bind_queues = [call.kwargs.get("queue") for call in ch.queue_bind.call_args_list]
    assert "user_events_queue.dlq" in bind_queues
