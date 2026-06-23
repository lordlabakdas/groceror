"""
Top-level pytest configuration and session-scoped fixtures.

Fixtures defined here are available to all tests under tests/.
"""
from unittest.mock import patch

import pytest

from tests._client import client as _shared_client


@pytest.fixture(scope="session", autouse=True)
def mock_send_sms():
    """Prevent tests from making real Twilio API calls."""
    with patch("api.helpers.auth_helper.send_sms") as m:
        yield m


@pytest.fixture(scope="session")
def client():
    """Session-scoped TestClient shared across all test files.

    Returns the same instance used by integration helpers so that only
    one portal thread (and one DB connection) is active during the run.
    """
    return _shared_client
