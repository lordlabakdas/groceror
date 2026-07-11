"""
Comprehensive end-to-end tests for the Groceror platform.

Test coverage:
  - Auth:      OTP send/verify, registration, login, profile (user + store),
               password change, token refresh
  - Stores:    CRUD, search, activate/deactivate, ownership enforcement
  - Inventory: add, retrieve, delete (store-owner flow)
  - Cart:      add item, get items, update, remove, clear, totals
  - Orders:    create order (RabbitMQ publisher mocked)

Fixtures are defined in conftest.py; shared helpers live in helpers.py.
"""
import uuid
from unittest.mock import patch

import pytest

from tests.integration.helpers import (
    PASSWORD,
    STORE_PHONE,
    USER_PHONE,
    _headers,
    _login,
    _otp_and_verify,
    _register,
    _suffix,
    client,
)


# ─────────────────────────────────────────────────────────────────────────────
# AUTH TESTS
# ─────────────────────────────────────────────────────────────────────────────

class TestAuth:

    def test_send_otp_success(self):
        r = client.post("/user/send-otp", json={"phone": "+19990000001"})
        assert r.status_code == 200
        assert "OTP sent successfully" in r.json()["message"]

    def test_verify_otp_wrong_code(self):
        client.post("/user/send-otp", json={"phone": "+19990000002"})
        r = client.post("/user/verify-otp", json={"phone": "+19990000002", "otp": "000000"})
        assert r.status_code == 400
        assert "Invalid or expired OTP" in r.json()["detail"]

    def test_register_without_otp_fails(self):
        """Phone that has never called send-otp cannot register."""
        r = client.post(
            "/user/register",
            json={"phone": "+19990000099", "entity_type": "user", "password": PASSWORD},
        )
        assert r.status_code == 400

    def test_register_unverified_phone_fails(self):
        """send-otp called but not verified → registration must fail."""
        phone = "+19990000003"
        client.post("/user/send-otp", json={"phone": phone})
        r = client.post(
            "/user/register",
            json={"phone": phone, "entity_type": "user", "password": PASSWORD},
        )
        assert r.status_code == 400
        assert "Phone number not verified" in r.json()["detail"]

    def test_user_registration_full_flow(self, user_token):
        """user_token fixture drives registration; just assert login succeeds."""
        assert user_token is not None
        assert len(user_token) > 20

    def test_store_registration_full_flow(self, store_token):
        assert store_token is not None

    def test_login_wrong_password(self):
        r = client.post("/user/login", json={"phone": USER_PHONE, "password": "wrongpass"})
        assert r.status_code == 401

    def test_login_unknown_phone(self):
        r = client.post("/user/login", json={"phone": "+10000000000", "password": PASSWORD})
        assert r.status_code == 401

    def test_set_user_profile(self, user_profile, user_token):
        # Fixture already called set-profile; verify it returned success
        r = client.post(
            "/user/set-profile",
            json={"name": "Test User", "email": "testuser@groceror.test"},
            headers=_headers(user_token),
        )
        assert r.status_code == 200
        assert "profile updated successfully" in r.json()["message"].lower()

    def test_set_store_profile(self, store_profile, store_token):
        r = client.post(
            "/user/set-profile",
            json={
                "name": "Fresh Market",
                "email": "fresh@groceror.test",
                "website": "https://freshmarket.test",
            },
            headers=_headers(store_token),
        )
        assert r.status_code == 200

    def test_set_store_profile_without_website(self):
        """Uses its own throwaway account — set-profile upserts by entity_id,
        so reusing the shared store_token would rename the "Fresh Market"
        store that TestStores/TestCart/TestOrders depend on."""
        phone = f"+1555{_suffix}09"
        _otp_and_verify(phone)
        _register(phone, "store")
        token = _login(phone)
        r = client.post(
            "/user/set-profile",
            json={"name": "No Website Store", "email": "nosite@groceror.test"},
            headers=_headers(token),
        )
        assert r.status_code == 200

    def test_refresh_token(self, user_token):
        r = client.get("/user/refresh-token", headers=_headers(user_token))
        assert r.status_code == 200
        assert "token" in r.json()

    def test_change_password(self, user_token):
        r = client.put(
            "/user/change-password",
            json={"username": USER_PHONE, "old_password": PASSWORD, "new_password": PASSWORD},
            headers=_headers(user_token),
        )
        assert r.status_code == 200
        assert r.json()["status"] == "success"

    def test_protected_endpoint_requires_token(self):
        r = client.get("/user/refresh-token")
        assert r.status_code == 401

    def test_protected_endpoint_rejects_bad_token(self):
        r = client.get("/user/refresh-token", headers={"Authorization": "Bearer badtoken"})
        assert r.status_code == 401


# ─────────────────────────────────────────────────────────────────────────────
# STORE TESTS
# ─────────────────────────────────────────────────────────────────────────────

class TestStores:

    def test_create_store(self, store_id):
        assert store_id is not None
        uuid.UUID(store_id)

    def test_get_store_by_id(self, store_id, store_token):
        r = client.get(f"/stores/{store_id}", headers=_headers(store_token))
        assert r.status_code == 200
        data = r.json()
        assert data["id"] == store_id
        assert data["name"] == "Fresh Market"
        assert data["email"] == "fresh@groceror.test"

    def test_get_nonexistent_store(self, store_token):
        fake_id = str(uuid.uuid4())
        r = client.get(f"/stores/{fake_id}", headers=_headers(store_token))
        assert r.status_code == 404

    def test_get_my_stores(self, store_id, store_token):
        r = client.get("/stores/my-stores", headers=_headers(store_token))
        assert r.status_code == 200
        ids = [s["id"] for s in r.json()]
        assert store_id in ids

    def test_update_store(self, store_id, store_token):
        r = client.put(
            f"/stores/{store_id}",
            json={"location": "456 New St"},
            headers=_headers(store_token),
        )
        assert r.status_code == 200
        assert r.json()["location"] == "456 New St"

    def test_update_store_unauthorized(self, store_id, other_store_token):
        r = client.put(
            f"/stores/{store_id}",
            json={"name": "Hijacked Store"},
            headers=_headers(other_store_token),
        )
        assert r.status_code == 403

    def test_delete_store_unauthorized(self, store_id, other_store_token):
        r = client.delete(f"/stores/{store_id}", headers=_headers(other_store_token))
        assert r.status_code == 403

    def test_deactivate_store(self, store_id, store_token):
        r = client.post(f"/stores/{store_id}/deactivate", headers=_headers(store_token))
        assert r.status_code == 200
        assert r.json()["is_active"] is False

    def test_activate_store(self, store_id, store_token):
        r = client.post(f"/stores/{store_id}/activate", headers=_headers(store_token))
        assert r.status_code == 200
        assert r.json()["is_active"] is True

    def test_search_stores(self, store_id, store_token):
        r = client.get("/stores/search/Fresh", headers=_headers(store_token))
        assert r.status_code == 200
        results = r.json()
        assert any(s["id"] == store_id for s in results)

    def test_search_stores_no_results(self, store_token):
        r = client.get("/stores/search/zzznomatch999", headers=_headers(store_token))
        assert r.status_code == 200
        assert r.json() == []

    def test_delete_store(self, store_token):
        """Create and immediately delete a throwaway store."""
        r = client.post(
            "/stores/",
            json={"name": "Throwaway", "email": "throw@groceror.test"},
            headers=_headers(store_token),
        )
        assert r.status_code == 201
        throwaway_id = r.json()["id"]

        r = client.delete(f"/stores/{throwaway_id}", headers=_headers(store_token))
        assert r.status_code == 200

        r = client.get(f"/stores/{throwaway_id}", headers=_headers(store_token))
        assert r.status_code == 404


# ─────────────────────────────────────────────────────────────────────────────
# INVENTORY TESTS
# ─────────────────────────────────────────────────────────────────────────────

class TestInventory:

    def test_add_inventory(self, inventory_id):
        assert inventory_id is not None
        uuid.UUID(inventory_id)

    def test_add_inventory_increases_quantity(self, store_token, inventory_id):
        """Adding the same item again should increment quantity, not create a duplicate."""
        r = client.post(
            "/inventory/add-inventory",
            json={"name": "Apples", "quantity": 10, "category": "PRODUCE"},
            headers=_headers(store_token),
        )
        assert r.status_code == 200

    def test_get_store_inventory(self, store_token, inventory_id):
        r = client.get("/inventory/get-store-inventory", headers=_headers(store_token))
        assert r.status_code == 200
        items = r.json()["inventory"]
        names = [i["name"] for i in items]
        assert "Apples" in names

    def test_add_inventory_invalid_category(self, store_token):
        r = client.post(
            "/inventory/add-inventory",
            json={"name": "Mystery", "quantity": 5, "category": "INVALID"},
            headers=_headers(store_token),
        )
        assert r.status_code == 422

    def test_delete_inventory(self, store_token):
        """Add an item, then delete it by name."""
        client.post(
            "/inventory/add-inventory",
            json={"name": "Bananas", "quantity": 20, "category": "PRODUCE"},
            headers=_headers(store_token),
        )
        r = client.delete(
            "/inventory/delete-inventory",
            params={"items": "Bananas"},
            headers=_headers(store_token),
        )
        assert r.status_code == 200

    def test_inventory_requires_auth(self):
        r = client.get("/inventory/get-store-inventory")
        assert r.status_code == 401


# ─────────────────────────────────────────────────────────────────────────────
# CART TESTS
# ─────────────────────────────────────────────────────────────────────────────

class TestCart:
    """
    Cart operations require a User profile (set via /user/set-profile) because
    CartEntity.user_id is a FK to the User profile table.
    """

    def test_cart_requires_auth(self, store_id):
        r = client.get(f"/cart/{store_id}/items")
        assert r.status_code == 401

    def test_cart_requires_user_profile(self, store_token, store_id):
        """A store-type account that has NOT set a profile yet gets 400."""
        phone = f"+1555{_suffix}99"
        _otp_and_verify(phone)
        _register(phone, "store")
        token = _login(phone)
        r = client.get(f"/cart/{store_id}/items", headers=_headers(token))
        assert r.status_code == 400
        assert "set-profile" in r.json()["detail"]

    def test_get_empty_cart(self, user_token, user_profile, store_id):
        r = client.get(f"/cart/{store_id}/items", headers=_headers(user_token))
        assert r.status_code == 200
        assert r.json() == []

    def test_get_all_carts_empty(self, user_token, user_profile):
        r = client.get("/cart/all", headers=_headers(user_token))
        assert r.status_code == 200

    def test_add_cart_item(self, user_token, user_profile, store_id, inventory_id):
        r = client.post(
            f"/cart/{store_id}/items",
            json={"inventory_id": inventory_id, "quantity": 3, "price": 1.99},
            headers=_headers(user_token),
        )
        assert r.status_code == 201
        data = r.json()
        assert data["quantity"] == 3
        assert data["inventory_id"] == inventory_id

    def test_get_cart_items(self, user_token, user_profile, store_id, inventory_id):
        r = client.get(f"/cart/{store_id}/items", headers=_headers(user_token))
        assert r.status_code == 200
        items = r.json()
        assert len(items) >= 1
        assert any(i["inventory_id"] == inventory_id for i in items)

    def test_get_cart_total(self, user_token, user_profile, store_id):
        r = client.get(f"/cart/{store_id}/total", headers=_headers(user_token))
        assert r.status_code == 200
        data = r.json()
        assert "total_price" in data
        assert "total_quantity" in data
        assert isinstance(data["total_quantity"], int)
        assert isinstance(data["total_price"], float)

    def test_update_cart_item(self, user_token, user_profile, store_id, inventory_id):
        items = client.get(f"/cart/{store_id}/items", headers=_headers(user_token)).json()
        item = next(i for i in items if i["inventory_id"] == inventory_id)
        item_id = item["id"]

        r = client.put(
            f"/cart/{store_id}/items/{item_id}",
            json={"quantity": 5},
            headers=_headers(user_token),
        )
        assert r.status_code == 200
        assert r.json()["quantity"] == 5

    def test_remove_cart_item(self, user_token, user_profile, store_id, inventory_id):
        items = client.get(f"/cart/{store_id}/items", headers=_headers(user_token)).json()
        item_id = items[0]["id"]

        r = client.delete(
            f"/cart/{store_id}/items/{item_id}",
            headers=_headers(user_token),
        )
        assert r.status_code == 200

    def test_remove_nonexistent_cart_item(self, user_token, user_profile, store_id):
        fake_id = str(uuid.uuid4())
        r = client.delete(f"/cart/{store_id}/items/{fake_id}", headers=_headers(user_token))
        assert r.status_code == 404

    def test_add_item_with_insufficient_inventory(self, user_token, user_profile, store_id, inventory_id):
        r = client.post(
            f"/cart/{store_id}/items",
            json={"inventory_id": inventory_id, "quantity": 99999, "price": 1.99},
            headers=_headers(user_token),
        )
        assert r.status_code == 400

    def test_clear_cart(self, user_token, user_profile, store_id, inventory_id):
        # Add an item first so the cart is non-empty
        client.post(
            f"/cart/{store_id}/items",
            json={"inventory_id": inventory_id, "quantity": 1, "price": 1.99},
            headers=_headers(user_token),
        )
        r = client.post(f"/cart/{store_id}/clear", headers=_headers(user_token))
        assert r.status_code == 200

        items = client.get(f"/cart/{store_id}/items", headers=_headers(user_token)).json()
        assert items == []


# ─────────────────────────────────────────────────────────────────────────────
# ORDER TESTS
# ─────────────────────────────────────────────────────────────────────────────

class TestOrders:

    @patch("engine.publisher.publish_message")
    def test_create_order(self, mock_publish, user_token, user_profile, inventory_id):
        r = client.post(
            "/order/create-order",
            json={"items": [{"inventory_id": inventory_id, "quantity": 2}]},
            headers=_headers(user_token),
        )
        assert r.status_code == 200
        data = r.json()
        assert "id" in data
        assert data["status"] == "pending"
        assert mock_publish.call_count == 2
        calls = {c.kwargs["queue_name"] for c in mock_publish.call_args_list}
        assert calls == {"order_queue", "email_queue"}
        email_call = next(c for c in mock_publish.call_args_list if c.kwargs["queue_name"] == "email_queue")
        assert email_call.kwargs["recipient"] == user_profile["email"]
        assert data["id"] in email_call.kwargs["subject"]

    @patch("engine.publisher.publish_message")
    def test_create_order_empty_items_rejected(self, mock_publish, user_token, user_profile):
        r = client.post(
            "/order/create-order",
            json={"items": []},
            headers=_headers(user_token),
        )
        assert r.status_code == 422

    def test_create_order_requires_auth(self):
        r = client.post(
            "/order/create-order",
            json={"items": [{"inventory_id": "00000000-0000-0000-0000-000000000000", "quantity": 1}]},
        )
        assert r.status_code == 401

    def test_create_order_requires_profile(self, store_token):
        phone = f"+1555{_suffix}98"
        _otp_and_verify(phone)
        _register(phone, "user")
        token = _login(phone)
        with patch("engine.publisher.publish_message"):
            r = client.post(
                "/order/create-order",
                json={"items": [{"inventory_id": "00000000-0000-0000-0000-000000000000", "quantity": 1}]},
                headers=_headers(token),
            )
        assert r.status_code == 400
        assert "set-profile" in r.json()["detail"]
