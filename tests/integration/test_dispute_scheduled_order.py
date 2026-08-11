"""
Integration tests for the Dispute and Scheduled Order APIs.

Test coverage:
  - Disputes:        open, list, get, add message, resolve, close,
                      ownership/authorization enforcement, status transitions
  - Scheduled Orders: create, list (with auto-fire of overdue orders),
                      update, run-now, delete, validation errors

Design note on isolation: dispute_api / scheduled_order_api resolve "the
current store" for a store-type token via `select(Store).where(Store.entity_id
== entity.id).first()`. Because `POST /stores/` (unlike `/user/set-profile`)
always INSERTs a new Store row rather than upserting, reusing the shared
`store_token` / `store_id` fixtures from conftest.py across multiple parallel
test files could leave more than one Store row for the same entity_id in the
session-wide SQLite DB, making `.first()` resolve to a different store than
the one this file's fixture created. To keep these tests fully deterministic
regardless of what other test files do in the same pytest session, this file
mints its own dedicated store accounts (unique phone numbers) rather than
relying on the shared store_token/store_id/store_profile/inventory_id
fixtures. The shared `user_token` / `user_profile` fixtures ARE reused here,
because `/user/set-profile` upserts a single User row per entity_id, so they
are safe to share across files.
"""
import uuid
from datetime import date, timedelta
from unittest.mock import patch

import pytest

from tests.integration.helpers import (
    _headers,
    _login,
    _otp_and_verify,
    _register,
    client,
)

# ─────────────────────────────────────────────────────────────────────────────
# Unique phone numbers for this file (isolated from every other test file's
# accounts, per the +1558{_suffix}NN convention).
# ─────────────────────────────────────────────────────────────────────────────
_suffix = str(uuid.uuid4().int)[:6]

PRIMARY_STORE_PHONE = f"+1558{_suffix}01"
SECONDARY_STORE_PHONE = f"+1558{_suffix}02"
NO_PROFILE_USER_PHONE = f"+1558{_suffix}03"
NO_PROFILE_STORE_PHONE = f"+1558{_suffix}04"
OTHER_USER_PHONE = f"+1558{_suffix}05"


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def primary_store_token():
    _otp_and_verify(PRIMARY_STORE_PHONE)
    _register(PRIMARY_STORE_PHONE, "store")
    return _login(PRIMARY_STORE_PHONE)


@pytest.fixture(scope="module")
def primary_store_id(primary_store_token):
    r = client.post(
        "/stores/",
        json={
            "name": "Primary Test Store",
            "email": "primarystore@groceror.test",
            "website": "https://primarystore.test",
            "location": "1 Primary St",
        },
        headers=_headers(primary_store_token),
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


@pytest.fixture(scope="module")
def dispute_inventory_id(primary_store_token, primary_store_id):
    r = client.post(
        "/inventory/add-inventory",
        json={"name": "Dispute Widget", "quantity": 100, "category": "PRODUCE", "price": 9.99},
        headers=_headers(primary_store_token),
    )
    assert r.status_code == 200, r.text
    return r.json()["inventory_id"]


@pytest.fixture(scope="module")
def sched_inventory_id(primary_store_token, primary_store_id):
    r = client.post(
        "/inventory/add-inventory",
        json={"name": "Scheduled Widget", "quantity": 200, "category": "GROCERY", "price": 4.5},
        headers=_headers(primary_store_token),
    )
    assert r.status_code == 200, r.text
    return r.json()["inventory_id"]


@pytest.fixture(scope="module")
def sched_deletable_inventory_id(primary_store_token, primary_store_id):
    r = client.post(
        "/inventory/add-inventory",
        json={"name": "Deletable Widget", "quantity": 50, "category": "OTHER", "price": 1.25},
        headers=_headers(primary_store_token),
    )
    assert r.status_code == 200, r.text
    return r.json()["inventory_id"]


@pytest.fixture(scope="module")
def secondary_store_token():
    _otp_and_verify(SECONDARY_STORE_PHONE)
    _register(SECONDARY_STORE_PHONE, "store")
    return _login(SECONDARY_STORE_PHONE)


@pytest.fixture(scope="module")
def secondary_store_id(secondary_store_token):
    r = client.post(
        "/stores/",
        json={
            "name": "Secondary Test Store",
            "email": "secondarystore@groceror.test",
            "website": "https://secondarystore.test",
            "location": "2 Secondary St",
        },
        headers=_headers(secondary_store_token),
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


@pytest.fixture(scope="module")
def secondary_inventory_id(secondary_store_token, secondary_store_id):
    r = client.post(
        "/inventory/add-inventory",
        json={"name": "Other Store Widget", "quantity": 30, "category": "DAIRY", "price": 3.0},
        headers=_headers(secondary_store_token),
    )
    assert r.status_code == 200, r.text
    return r.json()["inventory_id"]


@pytest.fixture(scope="module")
def no_profile_user_token():
    """Registered + logged in, but /user/set-profile was never called."""
    _otp_and_verify(NO_PROFILE_USER_PHONE)
    _register(NO_PROFILE_USER_PHONE, "user")
    return _login(NO_PROFILE_USER_PHONE)


@pytest.fixture(scope="module")
def no_profile_store_token():
    """Registered as a store, but neither /user/set-profile nor POST /stores/
    was ever called, so no Store row exists for this entity."""
    _otp_and_verify(NO_PROFILE_STORE_PHONE)
    _register(NO_PROFILE_STORE_PHONE, "store")
    return _login(NO_PROFILE_STORE_PHONE)


@pytest.fixture(scope="module")
def other_user_token():
    _otp_and_verify(OTHER_USER_PHONE)
    _register(OTHER_USER_PHONE, "user")
    return _login(OTHER_USER_PHONE)


@pytest.fixture(scope="module")
def other_user_profile(other_user_token):
    r = client.post(
        "/user/set-profile",
        json={"name": "Other Shopper", "email": "othershopper@groceror.test"},
        headers=_headers(other_user_token),
    )
    assert r.status_code == 200, r.text
    return {"name": "Other Shopper", "email": "othershopper@groceror.test"}


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _place_order(token: str, inventory_id: str, quantity: int = 1) -> str:
    with patch("engine.mailer.Mailer.send"):
        r = client.post(
            "/order/create-order",
            json={"items": [{"inventory_id": inventory_id, "quantity": quantity}]},
            headers=_headers(token),
        )
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _open_dispute(token: str, order_id: str, reason: str = "wrong_item", description: str = "Wrong item received"):
    r = client.post(
        "/disputes",
        json={"order_id": order_id, "reason": reason, "description": description},
        headers=_headers(token),
    )
    assert r.status_code == 200, r.text
    return r.json()


# ─────────────────────────────────────────────────────────────────────────────
# DISPUTE TESTS
# ─────────────────────────────────────────────────────────────────────────────

class TestDisputes:

    # -- open_dispute -----------------------------------------------------

    def test_open_dispute_requires_shopper(self, primary_store_token):
        r = client.post(
            "/disputes",
            json={"order_id": str(uuid.uuid4()), "reason": "wrong_item", "description": "x"},
            headers=_headers(primary_store_token),
        )
        assert r.status_code == 403
        assert "Shopper access only" in r.json()["detail"]

    def test_open_dispute_requires_user_profile(self, no_profile_user_token):
        r = client.post(
            "/disputes",
            json={"order_id": str(uuid.uuid4()), "reason": "wrong_item", "description": "x"},
            headers=_headers(no_profile_user_token),
        )
        assert r.status_code == 400
        assert "User profile not set" in r.json()["detail"]

    def test_open_dispute_invalid_reason(self, user_token, user_profile, dispute_inventory_id):
        order_id = _place_order(user_token, dispute_inventory_id)
        r = client.post(
            "/disputes",
            json={"order_id": order_id, "reason": "not_a_real_reason", "description": "x"},
            headers=_headers(user_token),
        )
        assert r.status_code == 400
        assert "Invalid reason" in r.json()["detail"]

    def test_open_dispute_order_not_found(self, user_token, user_profile):
        r = client.post(
            "/disputes",
            json={"order_id": str(uuid.uuid4()), "reason": "wrong_item", "description": "x"},
            headers=_headers(user_token),
        )
        assert r.status_code == 404
        assert "Order not found" in r.json()["detail"]

    def test_open_dispute_duplicate_conflict(self, user_token, user_profile, dispute_inventory_id):
        order_id = _place_order(user_token, dispute_inventory_id)
        _open_dispute(user_token, order_id)
        r = client.post(
            "/disputes",
            json={"order_id": order_id, "reason": "missing_item", "description": "again"},
            headers=_headers(user_token),
        )
        assert r.status_code == 409
        assert "already exists" in r.json()["detail"]

    def test_open_dispute_success(self, user_token, user_profile, dispute_inventory_id, primary_store_id):
        order_id = _place_order(user_token, dispute_inventory_id)
        data = _open_dispute(user_token, order_id, reason="damaged", description="It arrived broken")
        assert data["order_id"] == order_id
        assert data["store_id"] == primary_store_id
        assert data["reason"] == "damaged"
        assert data["description"] == "It arrived broken"
        assert data["status"] == "open"
        assert data["resolution"] is None
        assert data["messages"] == []
        uuid.UUID(data["id"])

    # -- list_disputes ------------------------------------------------------

    def test_list_disputes_requires_user_profile(self, no_profile_user_token):
        r = client.get("/disputes", headers=_headers(no_profile_user_token))
        assert r.status_code == 400
        assert "User profile not set" in r.json()["detail"]

    def test_list_disputes_requires_store_profile(self, no_profile_store_token):
        r = client.get("/disputes", headers=_headers(no_profile_store_token))
        assert r.status_code == 400
        assert "Store profile not set" in r.json()["detail"]

    def test_list_disputes_as_user(self, user_token, user_profile, dispute_inventory_id):
        order_id = _place_order(user_token, dispute_inventory_id)
        dispute = _open_dispute(user_token, order_id)
        r = client.get("/disputes", headers=_headers(user_token))
        assert r.status_code == 200
        ids = [d["id"] for d in r.json()]
        assert dispute["id"] in ids

    def test_list_disputes_as_store(self, user_token, user_profile, dispute_inventory_id, primary_store_token):
        order_id = _place_order(user_token, dispute_inventory_id)
        dispute = _open_dispute(user_token, order_id)
        r = client.get("/disputes", headers=_headers(primary_store_token))
        assert r.status_code == 200
        ids = [d["id"] for d in r.json()]
        assert dispute["id"] in ids

    # -- get_dispute ----------------------------------------------------------

    def test_get_dispute_not_found(self, user_token, user_profile):
        r = client.get(f"/disputes/{uuid.uuid4()}", headers=_headers(user_token))
        assert r.status_code == 404

    def test_get_dispute_success_as_owning_user(self, user_token, user_profile, dispute_inventory_id):
        order_id = _place_order(user_token, dispute_inventory_id)
        dispute = _open_dispute(user_token, order_id)
        r = client.get(f"/disputes/{dispute['id']}", headers=_headers(user_token))
        assert r.status_code == 200
        assert r.json()["id"] == dispute["id"]

    def test_get_dispute_success_as_owning_store(self, user_token, user_profile, dispute_inventory_id, primary_store_token):
        order_id = _place_order(user_token, dispute_inventory_id)
        dispute = _open_dispute(user_token, order_id)
        r = client.get(f"/disputes/{dispute['id']}", headers=_headers(primary_store_token))
        assert r.status_code == 200
        assert r.json()["id"] == dispute["id"]

    def test_get_dispute_access_denied_wrong_user(self, user_token, user_profile, dispute_inventory_id, other_user_token, other_user_profile):
        order_id = _place_order(user_token, dispute_inventory_id)
        dispute = _open_dispute(user_token, order_id)
        r = client.get(f"/disputes/{dispute['id']}", headers=_headers(other_user_token))
        assert r.status_code == 403
        assert "Access denied" in r.json()["detail"]

    def test_get_dispute_access_denied_wrong_store(self, user_token, user_profile, dispute_inventory_id, secondary_store_token, secondary_store_id):
        order_id = _place_order(user_token, dispute_inventory_id)
        dispute = _open_dispute(user_token, order_id)
        r = client.get(f"/disputes/{dispute['id']}", headers=_headers(secondary_store_token))
        assert r.status_code == 403
        assert "Access denied" in r.json()["detail"]

    # -- add_message ----------------------------------------------------------

    def test_add_message_not_found(self, user_token, user_profile):
        r = client.post(
            f"/disputes/{uuid.uuid4()}/messages",
            json={"message": "hello"},
            headers=_headers(user_token),
        )
        assert r.status_code == 404

    def test_add_message_access_denied(self, user_token, user_profile, dispute_inventory_id, other_user_token, other_user_profile):
        order_id = _place_order(user_token, dispute_inventory_id)
        dispute = _open_dispute(user_token, order_id)
        r = client.post(
            f"/disputes/{dispute['id']}/messages",
            json={"message": "not yours"},
            headers=_headers(other_user_token),
        )
        assert r.status_code == 403

    def test_add_message_as_shopper_keeps_status_open(self, user_token, user_profile, dispute_inventory_id):
        order_id = _place_order(user_token, dispute_inventory_id)
        dispute = _open_dispute(user_token, order_id)
        r = client.post(
            f"/disputes/{dispute['id']}/messages",
            json={"message": "Any update on this?"},
            headers=_headers(user_token),
        )
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "open"
        assert any(m["sender_type"] == "shopper" and m["message"] == "Any update on this?" for m in data["messages"])

    def test_add_message_as_store_transitions_to_store_responded(self, user_token, user_profile, dispute_inventory_id, primary_store_token):
        order_id = _place_order(user_token, dispute_inventory_id)
        dispute = _open_dispute(user_token, order_id)
        r = client.post(
            f"/disputes/{dispute['id']}/messages",
            json={"message": "We're looking into it"},
            headers=_headers(primary_store_token),
        )
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "store_responded"
        assert any(m["sender_type"] == "store" for m in data["messages"])

    def test_add_message_on_resolved_dispute_rejected(self, user_token, user_profile, dispute_inventory_id, primary_store_token):
        order_id = _place_order(user_token, dispute_inventory_id)
        dispute = _open_dispute(user_token, order_id)
        r = client.put(
            f"/disputes/{dispute['id']}/resolve",
            json={"resolution": "refund"},
            headers=_headers(primary_store_token),
        )
        assert r.status_code == 200
        assert r.json()["status"] == "resolved"

        r = client.post(
            f"/disputes/{dispute['id']}/messages",
            json={"message": "too late"},
            headers=_headers(user_token),
        )
        assert r.status_code == 400
        assert "resolved or closed" in r.json()["detail"]

    # -- resolve_dispute --------------------------------------------------------

    def test_resolve_dispute_requires_store(self, user_token, user_profile):
        r = client.put(
            f"/disputes/{uuid.uuid4()}/resolve",
            json={"resolution": "refund"},
            headers=_headers(user_token),
        )
        assert r.status_code == 403
        assert "Store access only" in r.json()["detail"]

    def test_resolve_dispute_requires_store_profile(self, no_profile_store_token):
        r = client.put(
            f"/disputes/{uuid.uuid4()}/resolve",
            json={"resolution": "refund"},
            headers=_headers(no_profile_store_token),
        )
        assert r.status_code == 400
        assert "Store profile not set" in r.json()["detail"]

    def test_resolve_dispute_not_found(self, primary_store_token, primary_store_id):
        r = client.put(
            f"/disputes/{uuid.uuid4()}/resolve",
            json={"resolution": "refund"},
            headers=_headers(primary_store_token),
        )
        assert r.status_code == 404
        assert "Dispute not found" in r.json()["detail"]

    def test_resolve_dispute_wrong_store_returns_not_found(
        self, user_token, user_profile, dispute_inventory_id, secondary_store_token, secondary_store_id
    ):
        order_id = _place_order(user_token, dispute_inventory_id)
        dispute = _open_dispute(user_token, order_id)
        r = client.put(
            f"/disputes/{dispute['id']}/resolve",
            json={"resolution": "refund"},
            headers=_headers(secondary_store_token),
        )
        # Filtered by store_id, so a non-owning store just gets "not found",
        # not a 403 (unlike _get_authorized_dispute's generic access check).
        assert r.status_code == 404
        assert "Dispute not found" in r.json()["detail"]

    def test_resolve_dispute_invalid_resolution(self, user_token, user_profile, dispute_inventory_id, primary_store_token):
        order_id = _place_order(user_token, dispute_inventory_id)
        dispute = _open_dispute(user_token, order_id)
        r = client.put(
            f"/disputes/{dispute['id']}/resolve",
            json={"resolution": "not_a_real_resolution"},
            headers=_headers(primary_store_token),
        )
        assert r.status_code == 400
        assert "Invalid resolution" in r.json()["detail"]

    def test_resolve_dispute_success(self, user_token, user_profile, dispute_inventory_id, primary_store_token):
        order_id = _place_order(user_token, dispute_inventory_id)
        dispute = _open_dispute(user_token, order_id)
        r = client.put(
            f"/disputes/{dispute['id']}/resolve",
            json={"resolution": "replacement"},
            headers=_headers(primary_store_token),
        )
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "resolved"
        assert data["resolution"] == "replacement"

    # -- close_dispute ------------------------------------------------------

    def test_close_dispute_requires_user(self, primary_store_token):
        r = client.put(f"/disputes/{uuid.uuid4()}/close", headers=_headers(primary_store_token))
        assert r.status_code == 403
        assert "Shopper access only" in r.json()["detail"]

    def test_close_dispute_requires_user_profile(self, no_profile_user_token):
        r = client.put(f"/disputes/{uuid.uuid4()}/close", headers=_headers(no_profile_user_token))
        assert r.status_code == 400
        assert "User profile not set" in r.json()["detail"]

    def test_close_dispute_not_found(self, user_token, user_profile):
        r = client.put(f"/disputes/{uuid.uuid4()}/close", headers=_headers(user_token))
        assert r.status_code == 404
        assert "Dispute not found" in r.json()["detail"]

    def test_close_dispute_wrong_user_returns_not_found(
        self, user_token, user_profile, dispute_inventory_id, other_user_token, other_user_profile
    ):
        order_id = _place_order(user_token, dispute_inventory_id)
        dispute = _open_dispute(user_token, order_id)
        r = client.put(f"/disputes/{dispute['id']}/close", headers=_headers(other_user_token))
        assert r.status_code == 404

    def test_close_dispute_success(self, user_token, user_profile, dispute_inventory_id):
        order_id = _place_order(user_token, dispute_inventory_id)
        dispute = _open_dispute(user_token, order_id)
        r = client.put(f"/disputes/{dispute['id']}/close", headers=_headers(user_token))
        assert r.status_code == 200
        assert r.json()["status"] == "closed"

    # -- dead-code helpers: _get_user_optional / _get_store_optional --------
    #
    # These two functions are defined in dispute_api.py but are never wired
    # into any route via Depends(...) — no endpoint references them. There is
    # therefore no HTTP request that can exercise their bodies. They're
    # exercised directly here (as ordinary Python functions) purely to cover
    # those lines; this is not a real HTTP integration scenario.
    def test_get_user_optional_and_get_store_optional_dead_code(
        self, user_token, user_profile, primary_store_token, primary_store_id
    ):
        import asyncio

        from sqlmodel import select

        from api.dispute_api import _get_store_optional, _get_user_optional
        from models.db import db_session
        from models.entity.phone_verification import PhoneVerification
        from tests.integration.helpers import USER_PHONE

        user_entity = db_session.exec(
            select(PhoneVerification).where(PhoneVerification.phone == USER_PHONE)
        ).first()
        store_entity = db_session.exec(
            select(PhoneVerification).where(PhoneVerification.phone == PRIMARY_STORE_PHONE)
        ).first()
        assert user_entity is not None
        assert store_entity is not None

        # _get_user_optional/_get_store_optional are async (FastAPI Depends()
        # callables must be, to avoid the threadpool session-leak bug fixed
        # in this session — see get_current_user in api/user_api.py), so
        # calling them directly here requires awaiting them.
        async def run():
            found_user = await _get_user_optional(entity=user_entity)
            assert found_user is not None
            assert found_user.entity_id == user_entity.id

            # entity_type != "user" -> short-circuits to None
            assert await _get_user_optional(entity=store_entity) is None

            found_store = await _get_store_optional(entity=store_entity)
            assert found_store is not None
            assert found_store.entity_id == store_entity.id

            # entity_type != "store" -> short-circuits to None
            assert await _get_store_optional(entity=user_entity) is None

        asyncio.run(run())


# ─────────────────────────────────────────────────────────────────────────────
# SCHEDULED ORDER TESTS
# ─────────────────────────────────────────────────────────────────────────────

class TestScheduledOrders:

    # -- create_scheduled_order ----------------------------------------------

    def test_create_requires_user_profile(self, no_profile_user_token):
        r = client.post(
            "/scheduled-orders",
            json={"items": [{"inventory_id": str(uuid.uuid4()), "quantity": 1}], "frequency": "weekly"},
            headers=_headers(no_profile_user_token),
        )
        assert r.status_code == 400
        assert "User profile not set" in r.json()["detail"]

    def test_create_invalid_frequency(self, user_token, user_profile, sched_inventory_id):
        r = client.post(
            "/scheduled-orders",
            json={"items": [{"inventory_id": sched_inventory_id, "quantity": 1}], "frequency": "daily"},
            headers=_headers(user_token),
        )
        assert r.status_code == 400
        assert "frequency must be" in r.json()["detail"]

    def test_create_empty_items_rejected(self, user_token, user_profile):
        r = client.post(
            "/scheduled-orders",
            json={"items": [], "frequency": "weekly"},
            headers=_headers(user_token),
        )
        assert r.status_code == 400
        assert "At least one item required" in r.json()["detail"]

    def test_create_items_not_found(self, user_token, user_profile):
        r = client.post(
            "/scheduled-orders",
            json={"items": [{"inventory_id": str(uuid.uuid4()), "quantity": 1}], "frequency": "weekly"},
            headers=_headers(user_token),
        )
        assert r.status_code == 400
        assert "not found" in r.json()["detail"]

    def test_create_items_must_share_store(self, user_token, user_profile, sched_inventory_id, secondary_inventory_id):
        r = client.post(
            "/scheduled-orders",
            json={
                "items": [
                    {"inventory_id": sched_inventory_id, "quantity": 1},
                    {"inventory_id": secondary_inventory_id, "quantity": 1},
                ],
                "frequency": "weekly",
            },
            headers=_headers(user_token),
        )
        assert r.status_code == 400
        assert "same store" in r.json()["detail"]

    def test_create_success_default_start_date(self, user_token, user_profile, sched_inventory_id, primary_store_id):
        r = client.post(
            "/scheduled-orders",
            json={"items": [{"inventory_id": sched_inventory_id, "quantity": 2}], "frequency": "weekly"},
            headers=_headers(user_token),
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["store_id"] == primary_store_id
        assert data["store_name"] == "Primary Test Store"
        assert data["frequency"] == "weekly"
        assert data["is_active"] is True
        assert data["last_run_at"] is None
        assert data["next_run_date"] == str(date.today() + timedelta(days=7))
        assert len(data["items"]) == 1
        assert data["items"][0]["inventory_id"] == sched_inventory_id
        assert data["items"][0]["item_name"] == "Scheduled Widget"
        assert data["items"][0]["quantity"] == 2

    def test_create_success_explicit_start_date(self, user_token, user_profile, sched_inventory_id):
        explicit = date.today() + timedelta(days=3)
        r = client.post(
            "/scheduled-orders",
            json={
                "items": [{"inventory_id": sched_inventory_id, "quantity": 1}],
                "frequency": "monthly",
                "start_date": str(explicit),
            },
            headers=_headers(user_token),
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["frequency"] == "monthly"
        assert data["next_run_date"] == str(explicit)

    # -- list_scheduled_orders (incl. auto-fire of overdue orders) -----------

    def test_list_requires_user_profile(self, no_profile_user_token):
        r = client.get("/scheduled-orders", headers=_headers(no_profile_user_token))
        assert r.status_code == 400

    def test_list_does_not_fire_future_schedule(self, user_token, user_profile, sched_inventory_id):
        create = client.post(
            "/scheduled-orders",
            json={"items": [{"inventory_id": sched_inventory_id, "quantity": 1}], "frequency": "weekly"},
            headers=_headers(user_token),
        ).json()

        r = client.get("/scheduled-orders", headers=_headers(user_token))
        assert r.status_code == 200
        found = next(so for so in r.json() if so["id"] == create["id"])
        assert found["last_run_at"] is None
        assert found["next_run_date"] == create["next_run_date"]

    def test_list_autofires_overdue_active_schedule(self, user_token, user_profile, sched_inventory_id):
        past_start = date.today() - timedelta(days=1)
        create = client.post(
            "/scheduled-orders",
            json={
                "items": [{"inventory_id": sched_inventory_id, "quantity": 1}],
                "frequency": "weekly",
                "start_date": str(past_start),
            },
            headers=_headers(user_token),
        ).json()
        assert create["next_run_date"] == str(past_start)

        r = client.get("/scheduled-orders", headers=_headers(user_token))
        assert r.status_code == 200
        found = next(so for so in r.json() if so["id"] == create["id"])
        assert found["last_run_at"] is not None
        assert found["next_run_date"] == str(date.today() + timedelta(days=7))

    # -- update_scheduled_order ------------------------------------------------

    def test_update_not_found(self, user_token, user_profile):
        r = client.put(
            f"/scheduled-orders/{uuid.uuid4()}",
            json={"frequency": "monthly"},
            headers=_headers(user_token),
        )
        assert r.status_code == 404

    def test_update_invalid_frequency(self, user_token, user_profile, sched_inventory_id):
        create = client.post(
            "/scheduled-orders",
            json={"items": [{"inventory_id": sched_inventory_id, "quantity": 1}], "frequency": "weekly"},
            headers=_headers(user_token),
        ).json()
        r = client.put(
            f"/scheduled-orders/{create['id']}",
            json={"frequency": "daily"},
            headers=_headers(user_token),
        )
        assert r.status_code == 400
        assert "Invalid frequency" in r.json()["detail"]

    def test_update_change_frequency(self, user_token, user_profile, sched_inventory_id):
        create = client.post(
            "/scheduled-orders",
            json={"items": [{"inventory_id": sched_inventory_id, "quantity": 1}], "frequency": "weekly"},
            headers=_headers(user_token),
        ).json()
        r = client.put(
            f"/scheduled-orders/{create['id']}",
            json={"frequency": "biweekly"},
            headers=_headers(user_token),
        )
        assert r.status_code == 200
        assert r.json()["frequency"] == "biweekly"

    def test_update_toggle_is_active(self, user_token, user_profile, sched_inventory_id):
        create = client.post(
            "/scheduled-orders",
            json={"items": [{"inventory_id": sched_inventory_id, "quantity": 1}], "frequency": "weekly"},
            headers=_headers(user_token),
        ).json()
        assert create["is_active"] is True

        r = client.put(
            f"/scheduled-orders/{create['id']}",
            json={"is_active": False},
            headers=_headers(user_token),
        )
        assert r.status_code == 200
        assert r.json()["is_active"] is False

        r = client.put(
            f"/scheduled-orders/{create['id']}",
            json={"is_active": True},
            headers=_headers(user_token),
        )
        assert r.status_code == 200
        assert r.json()["is_active"] is True

    def test_update_wrong_user_returns_not_found(self, user_token, user_profile, sched_inventory_id, other_user_token, other_user_profile):
        create = client.post(
            "/scheduled-orders",
            json={"items": [{"inventory_id": sched_inventory_id, "quantity": 1}], "frequency": "weekly"},
            headers=_headers(user_token),
        ).json()
        r = client.put(
            f"/scheduled-orders/{create['id']}",
            json={"frequency": "monthly"},
            headers=_headers(other_user_token),
        )
        assert r.status_code == 404

    # -- run_now -------------------------------------------------------------

    def test_run_now_not_found(self, user_token, user_profile):
        r = client.post(f"/scheduled-orders/{uuid.uuid4()}/run-now", headers=_headers(user_token))
        assert r.status_code == 404
        assert "Scheduled order not found" in r.json()["detail"]

    def test_run_now_executes_regardless_of_next_run_date(self, user_token, user_profile, sched_inventory_id):
        create = client.post(
            "/scheduled-orders",
            json={"items": [{"inventory_id": sched_inventory_id, "quantity": 1}], "frequency": "weekly"},
            headers=_headers(user_token),
        ).json()
        assert create["last_run_at"] is None

        r = client.post(f"/scheduled-orders/{create['id']}/run-now", headers=_headers(user_token))
        assert r.status_code == 200
        data = r.json()
        assert data["last_run_at"] is not None
        assert data["next_run_date"] == str(date.today() + timedelta(days=7))

    def test_run_now_skips_silently_when_item_unavailable(
        self, user_token, user_profile, primary_store_token, sched_deletable_inventory_id
    ):
        create = client.post(
            "/scheduled-orders",
            json={"items": [{"inventory_id": sched_deletable_inventory_id, "quantity": 1}], "frequency": "weekly"},
            headers=_headers(user_token),
        ).json()

        # Remove the underlying inventory item so the OrderService raises
        # ValueError("Inventory items not found: ...") inside _execute().
        del_r = client.delete(
            "/inventory/delete-inventory",
            params={"items": "Deletable Widget"},
            headers=_headers(primary_store_token),
        )
        assert del_r.status_code == 200

        r = client.post(f"/scheduled-orders/{create['id']}/run-now", headers=_headers(user_token))
        # The ValueError is caught and swallowed inside _execute(); the
        # endpoint still returns 200 and still advances the schedule.
        assert r.status_code == 200
        data = r.json()
        assert data["last_run_at"] is not None
        assert data["next_run_date"] == str(date.today() + timedelta(days=7))

    # -- delete_scheduled_order ------------------------------------------------

    def test_delete_nonexistent_still_returns_204(self, user_token, user_profile):
        r = client.delete(f"/scheduled-orders/{uuid.uuid4()}", headers=_headers(user_token))
        assert r.status_code == 204

    def test_delete_wrong_user_is_a_silent_noop(self, user_token, user_profile, sched_inventory_id, other_user_token, other_user_profile):
        create = client.post(
            "/scheduled-orders",
            json={"items": [{"inventory_id": sched_inventory_id, "quantity": 1}], "frequency": "weekly"},
            headers=_headers(user_token),
        ).json()

        r = client.delete(f"/scheduled-orders/{create['id']}", headers=_headers(other_user_token))
        assert r.status_code == 204

        # Still present for the real owner since the delete matched no row.
        r = client.get("/scheduled-orders", headers=_headers(user_token))
        ids = [so["id"] for so in r.json()]
        assert create["id"] in ids

    def test_delete_success(self, user_token, user_profile, sched_inventory_id):
        create = client.post(
            "/scheduled-orders",
            json={"items": [{"inventory_id": sched_inventory_id, "quantity": 1}], "frequency": "weekly"},
            headers=_headers(user_token),
        ).json()

        r = client.delete(f"/scheduled-orders/{create['id']}", headers=_headers(user_token))
        assert r.status_code == 204

        r = client.get("/scheduled-orders", headers=_headers(user_token))
        ids = [so["id"] for so in r.json()]
        assert create["id"] not in ids
