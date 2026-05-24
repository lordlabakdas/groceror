"""Unit test configuration that doesn't require database."""
import pytest


@pytest.fixture
def mock_channel():
    """Mock channel fixture for publisher tests."""
    from unittest.mock import MagicMock
    return MagicMock()
