"""
Module-scoped pytest fixtures for integration tests.

These fixtures are automatically available to every test in the
tests/integration/ directory.  They drive the one-time setup that
creates real DB records (users, stores, inventory) used across
multiple test classes in test_platform.py.
"""
import pytest

from tests.integration.helpers import (
    client,
    _headers,
    _login,
    _otp_and_verify,
    _register,
    OTHER_PHONE,
    PASSWORD,
    STORE_PHONE,
    USER_PHONE,
)


@pytest.fixture(scope="module")
def user_token():
    _otp_and_verify(USER_PHONE)
    _register(USER_PHONE, "user")
    return _login(USER_PHONE)


@pytest.fixture(scope="module")
def store_token():
    _otp_and_verify(STORE_PHONE)
    _register(STORE_PHONE, "store")
    return _login(STORE_PHONE)


@pytest.fixture(scope="module")
def other_store_token():
    """A second store owner used for 403 ownership tests."""
    _otp_and_verify(OTHER_PHONE)
    _register(OTHER_PHONE, "store")
    return _login(OTHER_PHONE)


@pytest.fixture(scope="module")
def user_profile(user_token):
    """Set and return the user profile."""
    r = client.post(
        "/user/set-profile",
        json={"name": "Test User", "email": "testuser@groceror.test", "location": "User City"},
        headers=_headers(user_token),
    )
    assert r.status_code == 200, r.text
    return {"name": "Test User", "email": "testuser@groceror.test"}


@pytest.fixture(scope="module")
def store_id(store_token):
    """Create a store via the API and return its id."""
    r = client.post(
        "/stores/",
        json={
            "name": "Fresh Market",
            "email": "fresh@groceror.test",
            "website": "https://freshmarket.test",
            "location": "123 Market St",
        },
        headers=_headers(store_token),
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


@pytest.fixture(scope="module")
def store_profile(store_token, store_id):
    """Set the store profile.

    Depends on store_id so the store already exists; set-profile updates
    the existing store rather than inserting a second one.
    """
    r = client.post(
        "/user/set-profile",
        json={
            "name": "Fresh Market",
            "email": "fresh@groceror.test",
            "website": "https://freshmarket.test",
            "location": "123 Market St",
        },
        headers=_headers(store_token),
    )
    assert r.status_code == 200, r.text
    return {"name": "Fresh Market", "email": "fresh@groceror.test"}


@pytest.fixture(scope="module")
def inventory_id(store_token, store_id, store_profile):
    """Add an inventory item and return its id."""
    r = client.post(
        "/inventory/add-inventory",
        json={"name": "Apples", "quantity": 50, "category": "PRODUCE"},
        headers=_headers(store_token),
    )
    assert r.status_code == 200, r.text
    return r.json()["inventory_id"]
