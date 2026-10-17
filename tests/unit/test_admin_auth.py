"""Unit tests for api.helpers.admin_auth.require_admin_token.

Centralizes the check previously duplicated (and fixed) in store_api.py,
sponsored_post_api.py, and subscription_api.py — see ADMIN_TOKEN's removed
hardcoded default in config.py. The key property under test: an unset
ADMIN_TOKEN must deny every request, never behave like a wildcard match.
"""
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from api.helpers.admin_auth import require_admin_token
from config import AdminConfig


def test_rejects_when_token_unset_even_with_empty_header():
    with patch.object(AdminConfig, "ADMIN_TOKEN", ""):
        with pytest.raises(HTTPException) as exc:
            require_admin_token("")
        assert exc.value.status_code == 403


def test_rejects_when_token_unset_regardless_of_header_value():
    with patch.object(AdminConfig, "ADMIN_TOKEN", ""):
        with pytest.raises(HTTPException):
            require_admin_token("anything")


def test_rejects_wrong_token():
    with patch.object(AdminConfig, "ADMIN_TOKEN", "the-real-token"):
        with pytest.raises(HTTPException) as exc:
            require_admin_token("wrong")
        assert exc.value.status_code == 403


def test_accepts_matching_token():
    with patch.object(AdminConfig, "ADMIN_TOKEN", "the-real-token"):
        require_admin_token("the-real-token")  # must not raise
