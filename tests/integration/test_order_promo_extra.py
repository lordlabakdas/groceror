"""
Integration tests covering untested branches in:

  - api/order_api.py         (order history, store-orders listing,
                               status-update edge cases, error paths)
  - api/featured_store_api.py
  - api/flash_sale_api.py
  - api/back_in_stock_api.py

Happy-path order creation is already covered by test_platform.py's
TestOrders class; this file focuses on branches that weren't exercised
there: history/listing endpoints, validation failures, ownership checks,
and 404/403/400 paths.

All accounts used here are created fresh with unique phone numbers (see
`_suffix` below) so this file has no shared mutable state with
test_platform.py or any other test module -- each fixture builds its own
user/store/inventory graph.
"""
import uuid
from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from models.entity.featured_store_entity import FeaturedStore

from tests.integration.helpers import (
    _headers,
    _login,
    _otp_and_verify,
    _register,
    client,
)

# ─────────────────────────────────────────────────────────────────────────────
# Unique phone numbers for this module (never reused by other agents' files)
# ─────────────────────────────────────────────────────────────────────────────
_suffix = str(uuid.uuid4().int)[:6]


def _phone(n: str) -> str:
    return f"+1560{_suffix}{n}"


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures: order tests
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def promo_user_token():
    phone = _phone("01")
    _otp_and_verify(phone)
    _register(phone, "user")
    return _login(phone)


@pytest.fixture(scope="module")
def promo_user_profile(promo_user_token):
    r = client.post(
        "/user/set-profile",
        json={"name": "Promo User", "email": "promouser@groceror.test"},
        headers=_headers(promo_user_token),
    )
    assert r.status_code == 200, r.text
    return {"name": "Promo User", "email": "promouser@groceror.test"}


@pytest.fixture(scope="module")
def promo_store_token():
    phone = _phone("02")
    _otp_and_verify(phone)
    _register(phone, "store")
    return _login(phone)


@pytest.fixture(scope="module")
def promo_store_id(promo_store_token):
    r = client.post(
        "/stores/",
        json={"name": "Promo Grocer", "email": "promogrocer@groceror.test", "location": "1 Promo Ave"},
        headers=_headers(promo_store_token),
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


@pytest.fixture(scope="module")
def promo_store_profile(promo_store_token, promo_store_id):
    r = client.post(
        "/user/set-profile",
        json={"name": "Promo Grocer", "email": "promogrocer@groceror.test", "location": "1 Promo Ave"},
        headers=_headers(promo_store_token),
    )
    assert r.status_code == 200, r.text
    return {"name": "Promo Grocer", "email": "promogrocer@groceror.test"}


@pytest.fixture(scope="module")
def promo_inventory_id(promo_store_token, promo_store_id, promo_store_profile):
    r = client.post(
        "/inventory/add-inventory",
        json={"name": "Oranges", "quantity": 100, "category": "PRODUCE"},
        headers=_headers(promo_store_token),
    )
    assert r.status_code == 200, r.text
    return r.json()["inventory_id"]


@pytest.fixture(scope="module")
def promo_other_store_token():
    phone = _phone("03")
    _otp_and_verify(phone)
    _register(phone, "store")
    return _login(phone)


@pytest.fixture(scope="module")
def promo_other_store_profile(promo_other_store_token):
    r = client.post(
        "/user/set-profile",
        json={"name": "Rival Grocer", "email": "rivalgrocer@groceror.test"},
        headers=_headers(promo_other_store_token),
    )
    assert r.status_code == 200, r.text
    return {"name": "Rival Grocer", "email": "rivalgrocer@groceror.test"}


@pytest.fixture(scope="module")
def promo_other_inventory_id(promo_other_store_token, promo_other_store_profile):
    r = client.post(
        "/inventory/add-inventory",
        json={"name": "Grapes", "quantity": 30, "category": "PRODUCE"},
        headers=_headers(promo_other_store_token),
    )
    assert r.status_code == 200, r.text
    return r.json()["inventory_id"]


# ─────────────────────────────────────────────────────────────────────────────
# ORDER HISTORY
# ─────────────────────────────────────────────────────────────────────────────

class TestOrderHistory:

    def test_order_history_empty_for_new_user(self, promo_user_token, promo_user_profile):
        r = client.get("/order/history", headers=_headers(promo_user_token))
        assert r.status_code == 200
        assert r.json() == {"orders": []}

    def test_create_order_then_history_has_items_and_store(
        self, promo_user_token, promo_user_profile, promo_inventory_id, promo_store_id, promo_store_profile
    ):
        with patch("engine.mailer.Mailer.send"):
            r = client.post(
                "/order/create-order",
                json={"items": [{"inventory_id": promo_inventory_id, "quantity": 3}]},
                headers=_headers(promo_user_token),
            )
        assert r.status_code == 200, r.text
        created = r.json()

        r2 = client.get("/order/history", headers=_headers(promo_user_token))
        assert r2.status_code == 200
        orders = r2.json()["orders"]
        match = next((o for o in orders if o["id"] == created["id"]), None)
        assert match is not None
        assert match["store_id"] == promo_store_id
        assert match["store_name"] == promo_store_profile["name"]
        assert match["status"] == "pending"
        assert len(match["items"]) == 1
        item = match["items"][0]
        assert item["inventory_id"] == promo_inventory_id
        assert item["name"] == "Oranges"
        assert item["quantity"] == 3


# ─────────────────────────────────────────────────────────────────────────────
# CREATE ORDER — error branches not covered by test_platform.py
# ─────────────────────────────────────────────────────────────────────────────

class TestCreateOrderErrors:

    def test_create_order_missing_inventory(self, promo_user_token, promo_user_profile):
        fake_id = str(uuid.uuid4())
        r = client.post(
            "/order/create-order",
            json={"items": [{"inventory_id": fake_id, "quantity": 1}]},
            headers=_headers(promo_user_token),
        )
        assert r.status_code == 400
        assert "not found" in r.json()["detail"]

    def test_create_order_invalid_coupon(self, promo_user_token, promo_user_profile, promo_inventory_id):
        r = client.post(
            "/order/create-order",
            json={
                "items": [{"inventory_id": promo_inventory_id, "quantity": 1}],
                "coupon_code": "NOSUCHCOUPON",
            },
            headers=_headers(promo_user_token),
        )
        assert r.status_code == 400
        assert "is not valid" in r.json()["detail"]

    def test_create_order_items_from_different_stores_rejected(
        self, promo_user_token, promo_user_profile, promo_inventory_id, promo_other_inventory_id
    ):
        r = client.post(
            "/order/create-order",
            json={
                "items": [
                    {"inventory_id": promo_inventory_id, "quantity": 1},
                    {"inventory_id": promo_other_inventory_id, "quantity": 1},
                ]
            },
            headers=_headers(promo_user_token),
        )
        assert r.status_code == 400
        assert "same store" in r.json()["detail"]

    def test_create_order_mailer_failure_still_succeeds(
        self, promo_user_token, promo_user_profile, promo_inventory_id
    ):
        with patch("engine.mailer.Mailer.send", side_effect=Exception("smtp down")):
            r = client.post(
                "/order/create-order",
                json={"items": [{"inventory_id": promo_inventory_id, "quantity": 1}]},
                headers=_headers(promo_user_token),
            )
        assert r.status_code == 200
        assert r.json()["status"] == "pending"


# ─────────────────────────────────────────────────────────────────────────────
# STORE ORDERS listing + auth guards
# ─────────────────────────────────────────────────────────────────────────────

class TestStoreOrders:

    def test_get_store_orders_requires_store_account(self, promo_user_token, promo_user_profile):
        r = client.get("/order/store-orders", headers=_headers(promo_user_token))
        assert r.status_code == 403
        assert r.json()["detail"] == "Store access only"

    def test_get_store_orders_requires_store_profile(self):
        phone = _phone("04")
        _otp_and_verify(phone)
        _register(phone, "store")
        token = _login(phone)
        r = client.get("/order/store-orders", headers=_headers(token))
        assert r.status_code == 400
        assert "set-profile" in r.json()["detail"]

    def test_get_store_orders_empty_for_store_without_orders(self):
        phone = _phone("05")
        _otp_and_verify(phone)
        _register(phone, "store")
        token = _login(phone)
        r = client.post(
            "/user/set-profile",
            json={"name": "Empty Grocer", "email": "emptygrocer@groceror.test"},
            headers=_headers(token),
        )
        assert r.status_code == 200
        r2 = client.get("/order/store-orders", headers=_headers(token))
        assert r2.status_code == 200
        assert r2.json() == {"orders": []}

    def test_get_store_orders_lists_created_order(
        self, promo_user_token, promo_user_profile, promo_store_token, promo_inventory_id
    ):
        with patch("engine.mailer.Mailer.send"):
            r = client.post(
                "/order/create-order",
                json={"items": [{"inventory_id": promo_inventory_id, "quantity": 2}]},
                headers=_headers(promo_user_token),
            )
        assert r.status_code == 200, r.text
        order_id = r.json()["id"]

        r2 = client.get("/order/store-orders", headers=_headers(promo_store_token))
        assert r2.status_code == 200
        orders = r2.json()["orders"]
        match = next((o for o in orders if o["id"] == order_id), None)
        assert match is not None
        assert match["status"] == "pending"
        assert len(match["items"]) == 1
        assert match["items"][0]["inventory_id"] == promo_inventory_id
        assert match["items"][0]["quantity"] == 2


# ─────────────────────────────────────────────────────────────────────────────
# UPDATE ORDER STATUS
# ─────────────────────────────────────────────────────────────────────────────

class TestUpdateOrderStatus:

    def test_update_order_status_requires_store_account(self, promo_user_token, promo_user_profile):
        fake_id = str(uuid.uuid4())
        r = client.put(
            f"/order/{fake_id}/status",
            json={"status": "confirmed"},
            headers=_headers(promo_user_token),
        )
        assert r.status_code == 403

    def test_update_order_status_invalid_status_value(self, promo_store_token, promo_store_profile):
        fake_id = str(uuid.uuid4())
        r = client.put(
            f"/order/{fake_id}/status",
            json={"status": "not-a-real-status"},
            headers=_headers(promo_store_token),
        )
        assert r.status_code == 400
        assert "Invalid status" in r.json()["detail"]

    def test_update_order_status_not_found(self, promo_store_token, promo_store_profile):
        fake_id = str(uuid.uuid4())
        r = client.put(
            f"/order/{fake_id}/status",
            json={"status": "confirmed"},
            headers=_headers(promo_store_token),
        )
        assert r.status_code == 404
        assert r.json()["detail"] == "Order not found"

    def test_update_order_status_success(
        self, promo_user_token, promo_user_profile, promo_store_token, promo_inventory_id
    ):
        with patch("engine.mailer.Mailer.send"):
            r = client.post(
                "/order/create-order",
                json={"items": [{"inventory_id": promo_inventory_id, "quantity": 1}]},
                headers=_headers(promo_user_token),
            )
        assert r.status_code == 200, r.text
        order_id = r.json()["id"]

        r2 = client.put(
            f"/order/{order_id}/status",
            json={"status": "confirmed"},
            headers=_headers(promo_store_token),
        )
        assert r2.status_code == 200
        assert r2.json() == {"message": "Status updated", "status": "confirmed"}

    def test_update_order_status_wrong_store_is_404(
        self,
        promo_user_token,
        promo_user_profile,
        promo_inventory_id,
        promo_other_store_token,
        promo_other_store_profile,
    ):
        with patch("engine.mailer.Mailer.send"):
            r = client.post(
                "/order/create-order",
                json={"items": [{"inventory_id": promo_inventory_id, "quantity": 1}]},
                headers=_headers(promo_user_token),
            )
        assert r.status_code == 200, r.text
        order_id = r.json()["id"]

        # promo_other_store_token owns a *different* store, so this order
        # isn't theirs -> update_order_status filters by store_id and finds nothing.
        r2 = client.put(
            f"/order/{order_id}/status",
            json={"status": "ready"},
            headers=_headers(promo_other_store_token),
        )
        assert r2.status_code == 404


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures: featured-store tests
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def feat_store_token():
    phone = _phone("06")
    _otp_and_verify(phone)
    _register(phone, "store")
    return _login(phone)


@pytest.fixture(scope="module")
def feat_store_id(feat_store_token):
    r = client.post(
        "/stores/",
        json={"name": "Featured Grocer", "email": "featuredgrocer@groceror.test", "location": "9 Feature Ln"},
        headers=_headers(feat_store_token),
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


@pytest.fixture(scope="module")
def feat_store_profile(feat_store_token, feat_store_id):
    r = client.post(
        "/user/set-profile",
        json={"name": "Featured Grocer", "email": "featuredgrocer@groceror.test", "location": "9 Feature Ln"},
        headers=_headers(feat_store_token),
    )
    assert r.status_code == 200, r.text
    return {"name": "Featured Grocer", "email": "featuredgrocer@groceror.test"}


@pytest.fixture(scope="module")
def feat_store2_token():
    phone = _phone("07")
    _otp_and_verify(phone)
    _register(phone, "store")
    return _login(phone)


@pytest.fixture(scope="module")
def feat_store2_id(feat_store2_token):
    r = client.post(
        "/stores/",
        json={"name": "Second Featured Grocer", "email": "secondfeatured@groceror.test"},
        headers=_headers(feat_store2_token),
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


@pytest.fixture(scope="module")
def feat_store2_profile(feat_store2_token, feat_store2_id):
    r = client.post(
        "/user/set-profile",
        json={"name": "Second Featured Grocer", "email": "secondfeatured@groceror.test"},
        headers=_headers(feat_store2_token),
    )
    assert r.status_code == 200, r.text
    return {"name": "Second Featured Grocer", "email": "secondfeatured@groceror.test"}


# ─────────────────────────────────────────────────────────────────────────────
# FEATURED STORES — reachable-through-HTTP endpoint
# ─────────────────────────────────────────────────────────────────────────────

class TestFeaturedStoreHTTP:
    """
    Of featured_store_api.py's four routes, only GET /stores/feature/me is
    actually reachable over HTTP in this app (see TestFeaturedStoreDirect
    below for why the other three are not). This class covers what HTTP
    can reach: the shared `_get_store` auth/profile guard and the "not
    featured yet" branch of get_my_featured.
    """

    def test_get_my_featured_requires_store_account(self, promo_user_token, promo_user_profile):
        r = client.get("/stores/feature/me", headers=_headers(promo_user_token))
        assert r.status_code == 403
        assert r.json()["detail"] == "Store access only"

    def test_get_my_featured_requires_store_profile(self):
        phone = _phone("08")
        _otp_and_verify(phone)
        _register(phone, "store")
        token = _login(phone)
        r = client.get("/stores/feature/me", headers=_headers(token))
        assert r.status_code == 400
        assert r.json()["detail"] == "Store profile not set"

    def test_get_my_featured_none_when_not_featured(self, feat_store_token, feat_store_profile):
        r = client.get("/stores/feature/me", headers=_headers(feat_store_token))
        assert r.status_code == 200
        assert r.json() is None


class TestFeaturedStoreExtra:
    """
    PUT /stores/feature, DELETE /stores/feature, and GET /stores/featured
    used to be shadowed by store_api.py's catch-all /stores/{store_id}
    routes, since main.py registered store_apis before featured_store_apis
    (Starlette dispatches to the first route whose path pattern matches,
    and "feature"/"featured" are syntactically valid store_ids). Fixed in
    main.py by registering featured_store_apis first — these are now
    reachable over HTTP like any other endpoint.
    """

    def test_set_featured_create_then_update_existing(self, feat_store_token, feat_store_id, feat_store_profile):
        r = client.put(
            "/stores/feature",
            json={"tagline": "Fresh daily!", "priority": 5},
            headers=_headers(feat_store_token),
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["store_id"] == feat_store_id
        assert data["tagline"] == "Fresh daily!"
        assert data["priority"] == 5
        assert data["is_active"] is True

        # Second call must hit the "existing" update branch, not the insert branch.
        r2 = client.put(
            "/stores/feature",
            json={"tagline": "Now cheaper!", "priority": 9},
            headers=_headers(feat_store_token),
        )
        assert r2.status_code == 200, r2.text
        data2 = r2.json()
        assert data2["tagline"] == "Now cheaper!"
        assert data2["priority"] == 9
        assert data2["is_active"] is True

        # Confirm it's visible through the "me" endpoint too.
        r3 = client.get("/stores/feature/me", headers=_headers(feat_store_token))
        assert r3.status_code == 200
        assert r3.json()["tagline"] == "Now cheaper!"
        assert r3.json()["priority"] == 9

    def test_remove_featured_deactivates(self, feat_store_token, feat_store_id):
        client.put(
            "/stores/feature",
            json={"tagline": "temp", "priority": 1},
            headers=_headers(feat_store_token),
        )
        r = client.delete("/stores/feature", headers=_headers(feat_store_token))
        assert r.status_code == 204

        r2 = client.get("/stores/feature/me", headers=_headers(feat_store_token))
        assert r2.status_code == 200
        assert r2.json()["is_active"] is False

    def test_remove_featured_noop_when_never_featured(self, feat_store2_id, feat_store2_profile, feat_store2_token):
        # Should not raise even though there's no FeaturedStore row yet.
        r = client.delete("/stores/feature", headers=_headers(feat_store2_token))
        assert r.status_code == 204

    def test_list_featured_stores_filters_inactive_and_future(
        self, feat_store_id, feat_store2_id, feat_store2_profile, feat_store_token, feat_store2_token
    ):
        # store1: reactivate, currently within date range -> should be listed.
        r1 = client.put(
            "/stores/feature",
            json={
                "tagline": "Back on!",
                "priority": 5,
                "start_date": (date.today() - timedelta(days=1)).isoformat(),
                "end_date": (date.today() + timedelta(days=1)).isoformat(),
            },
            headers=_headers(feat_store_token),
        )
        assert r1.status_code == 200, r1.text

        # store2: active but starts in the future -> excluded.
        r2 = client.put(
            "/stores/feature",
            json={
                "tagline": "Coming soon",
                "priority": 50,
                "start_date": (date.today() + timedelta(days=5)).isoformat(),
            },
            headers=_headers(feat_store2_token),
        )
        assert r2.status_code == 200, r2.text

        r3 = client.get("/stores/featured")
        assert r3.status_code == 200
        ids = {row["store_id"] for row in r3.json()}
        assert feat_store_id in ids
        assert feat_store2_id not in ids

    def test_is_currently_active_branches(self):
        from api.featured_store_api import _is_currently_active

        inactive = FeaturedStore(store_id=uuid.uuid4(), is_active=False)
        assert _is_currently_active(inactive) is False

        not_yet_started = FeaturedStore(
            store_id=uuid.uuid4(), is_active=True, start_date=date.today() + timedelta(days=1)
        )
        assert _is_currently_active(not_yet_started) is False

        already_ended = FeaturedStore(
            store_id=uuid.uuid4(), is_active=True, end_date=date.today() - timedelta(days=1)
        )
        assert _is_currently_active(already_ended) is False

        currently_active = FeaturedStore(store_id=uuid.uuid4(), is_active=True)
        assert _is_currently_active(currently_active) is True


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures: flash sale tests
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def fs_store_token():
    phone = _phone("09")
    _otp_and_verify(phone)
    _register(phone, "store")
    return _login(phone)


@pytest.fixture(scope="module")
def fs_store_profile(fs_store_token):
    r = client.post(
        "/user/set-profile",
        json={"name": "Flash Grocer", "email": "flashgrocer@groceror.test"},
        headers=_headers(fs_store_token),
    )
    assert r.status_code == 200, r.text
    return {"name": "Flash Grocer", "email": "flashgrocer@groceror.test"}


@pytest.fixture(scope="module")
def fs_inventory_id(fs_store_token, fs_store_profile):
    r = client.post(
        "/inventory/add-inventory",
        json={"name": "Salmon", "quantity": 20, "category": "MEAT", "price": 10.0},
        headers=_headers(fs_store_token),
    )
    assert r.status_code == 200, r.text
    return r.json()["inventory_id"]


@pytest.fixture(scope="module")
def fs_other_store_token():
    phone = _phone("10")
    _otp_and_verify(phone)
    _register(phone, "store")
    return _login(phone)


@pytest.fixture(scope="module")
def fs_other_store_profile(fs_other_store_token):
    r = client.post(
        "/user/set-profile",
        json={"name": "Rival Flash Grocer", "email": "rivalflash@groceror.test"},
        headers=_headers(fs_other_store_token),
    )
    assert r.status_code == 200, r.text
    return {"name": "Rival Flash Grocer", "email": "rivalflash@groceror.test"}


@pytest.fixture(scope="module")
def fs_sale(fs_store_token, fs_store_profile, fs_inventory_id):
    now = datetime.utcnow()
    payload = {
        "inventory_id": fs_inventory_id,
        "sale_price": 7.5,
        "start_at": (now - timedelta(minutes=1)).isoformat(),
        "end_at": (now + timedelta(hours=1)).isoformat(),
    }
    r = client.post("/flash-sales", json=payload, headers=_headers(fs_store_token))
    assert r.status_code == 200, r.text
    return r.json()


class TestFlashSaleCreateValidation:

    def test_create_requires_store_account(self, promo_user_token, promo_user_profile):
        now = datetime.utcnow()
        payload = {
            "inventory_id": str(uuid.uuid4()),
            "sale_price": 1.0,
            "start_at": now.isoformat(),
            "end_at": (now + timedelta(hours=1)).isoformat(),
        }
        r = client.post("/flash-sales", json=payload, headers=_headers(promo_user_token))
        assert r.status_code == 403
        assert r.json()["detail"] == "Store account required"

    def test_create_requires_store_profile(self):
        phone = _phone("11")
        _otp_and_verify(phone)
        _register(phone, "store")
        token = _login(phone)
        now = datetime.utcnow()
        payload = {
            "inventory_id": str(uuid.uuid4()),
            "sale_price": 1.0,
            "start_at": now.isoformat(),
            "end_at": (now + timedelta(hours=1)).isoformat(),
        }
        r = client.post("/flash-sales", json=payload, headers=_headers(token))
        assert r.status_code == 400
        assert r.json()["detail"] == "Store profile not set"

    def test_create_end_before_start_rejected(self, fs_store_token, fs_store_profile, fs_inventory_id):
        now = datetime.utcnow()
        payload = {
            "inventory_id": fs_inventory_id,
            "sale_price": 5.0,
            "start_at": now.isoformat(),
            "end_at": (now - timedelta(hours=1)).isoformat(),
        }
        r = client.post("/flash-sales", json=payload, headers=_headers(fs_store_token))
        assert r.status_code == 400
        assert "end_at must be after start_at" in r.json()["detail"]

    def test_create_end_in_past_rejected(self, fs_store_token, fs_store_profile, fs_inventory_id):
        # end_at is after start_at (passes the first check) but both are in the
        # past, isolating the second ("must be in the future") branch.
        start = datetime.utcnow() - timedelta(hours=3)
        end = datetime.utcnow() - timedelta(hours=1)
        payload = {
            "inventory_id": fs_inventory_id,
            "sale_price": 5.0,
            "start_at": start.isoformat(),
            "end_at": end.isoformat(),
        }
        r = client.post("/flash-sales", json=payload, headers=_headers(fs_store_token))
        assert r.status_code == 400
        assert "end_at must be in the future" in r.json()["detail"]

    def test_create_inventory_not_found(self, fs_store_token, fs_store_profile):
        now = datetime.utcnow()
        payload = {
            "inventory_id": str(uuid.uuid4()),
            "sale_price": 1.0,
            "start_at": now.isoformat(),
            "end_at": (now + timedelta(hours=1)).isoformat(),
        }
        r = client.post("/flash-sales", json=payload, headers=_headers(fs_store_token))
        assert r.status_code == 404
        assert r.json()["detail"] == "Inventory item not found"

    def test_create_inventory_belongs_to_other_store(
        self, fs_other_store_token, fs_other_store_profile, fs_inventory_id
    ):
        now = datetime.utcnow()
        payload = {
            "inventory_id": fs_inventory_id,
            "sale_price": 1.0,
            "start_at": now.isoformat(),
            "end_at": (now + timedelta(hours=1)).isoformat(),
        }
        r = client.post("/flash-sales", json=payload, headers=_headers(fs_other_store_token))
        assert r.status_code == 404
        assert r.json()["detail"] == "Inventory item not found"

    def test_create_sale_price_too_high_rejected(self, fs_store_token, fs_store_profile, fs_inventory_id):
        now = datetime.utcnow()
        payload = {
            "inventory_id": fs_inventory_id,
            "sale_price": 999.0,
            "start_at": now.isoformat(),
            "end_at": (now + timedelta(hours=1)).isoformat(),
        }
        r = client.post("/flash-sales", json=payload, headers=_headers(fs_store_token))
        assert r.status_code == 400
        assert "must be less than regular price" in r.json()["detail"]


class TestFlashSaleLifecycle:

    def test_create_success_fields(self, fs_sale):
        assert fs_sale["sale_price"] == 7.5
        assert fs_sale["original_price"] == 10.0
        assert fs_sale["is_active"] is True
        assert fs_sale["is_live"] is True
        assert fs_sale["seconds_remaining"] is not None
        assert fs_sale["seconds_remaining"] > 0
        # start_at/end_at must be tz-aware (UTC offset present) so a JS
        # `new Date(...)` on the receiving end doesn't misparse them as
        # local time — regression test for the grocer/shopper countdown
        # mismatch, which was caused by naive timestamps in the response.
        assert fs_sale["end_at"].endswith("+00:00") or fs_sale["end_at"].endswith("Z")
        assert fs_sale["start_at"].endswith("+00:00") or fs_sale["start_at"].endswith("Z")

    def test_create_accepts_tz_aware_timestamps(self, fs_store_token, fs_store_profile, fs_inventory_id):
        # The real frontend sends `Date.toISOString()`, which is tz-aware
        # (UTC, 'Z'-suffixed) — unlike this file's other fixtures, which use
        # naive `datetime.utcnow().isoformat()`. Regression test for a prod
        # bug where comparing an aware end_at against naive datetime.utcnow()
        # raised TypeError and 500'd every real-world creation.
        now = datetime.now(timezone.utc)
        payload = {
            "inventory_id": fs_inventory_id,
            "sale_price": 6.0,
            "start_at": now.isoformat(),
            "end_at": (now + timedelta(hours=2)).isoformat(),
        }
        assert payload["end_at"].endswith("+00:00")
        r = client.post("/flash-sales", json=payload, headers=_headers(fs_store_token))
        assert r.status_code == 200, r.text
        assert r.json()["is_live"] is True

    def test_list_store_flash_sales(self, fs_store_token, fs_sale):
        r = client.get("/flash-sales/store", headers=_headers(fs_store_token))
        assert r.status_code == 200
        assert any(s["id"] == fs_sale["id"] for s in r.json())

    def test_list_active_flash_sales_public_no_auth(self, fs_sale):
        r = client.get("/flash-sales/active")
        assert r.status_code == 200
        assert any(s["id"] == fs_sale["id"] for s in r.json())

    def test_cancel_requires_ownership(self, fs_other_store_token, fs_other_store_profile, fs_sale):
        r = client.delete(f"/flash-sales/{fs_sale['id']}", headers=_headers(fs_other_store_token))
        assert r.status_code == 404
        assert r.json()["detail"] == "Flash sale not found"

    def test_cancel_nonexistent(self, fs_store_token, fs_store_profile):
        r = client.delete(f"/flash-sales/{uuid.uuid4()}", headers=_headers(fs_store_token))
        assert r.status_code == 404

    def test_cancel_success(self, fs_store_token, fs_sale):
        r = client.delete(f"/flash-sales/{fs_sale['id']}", headers=_headers(fs_store_token))
        assert r.status_code == 204

        r2 = client.get("/flash-sales/active")
        assert all(s["id"] != fs_sale["id"] for s in r2.json())

        # list_store_flash_sales doesn't filter by is_active, so the
        # cancelled sale should still show up there, just deactivated.
        r3 = client.get("/flash-sales/store", headers=_headers(fs_store_token))
        cancelled = next(s for s in r3.json() if s["id"] == fs_sale["id"])
        assert cancelled["is_active"] is False
        assert cancelled["is_live"] is False

    def test_enrich_skips_sale_whose_inventory_was_deleted(self, fs_store_token, fs_store_profile):
        r = client.post(
            "/inventory/add-inventory",
            json={"name": "Doomed Item", "quantity": 5, "category": "OTHER", "price": 20.0},
            headers=_headers(fs_store_token),
        )
        assert r.status_code == 200, r.text
        inv_id = r.json()["inventory_id"]

        now = datetime.utcnow()
        payload = {
            "inventory_id": inv_id,
            "sale_price": 5.0,
            "start_at": (now - timedelta(minutes=1)).isoformat(),
            "end_at": (now + timedelta(hours=1)).isoformat(),
        }
        r2 = client.post("/flash-sales", json=payload, headers=_headers(fs_store_token))
        assert r2.status_code == 200, r2.text
        sale_id = r2.json()["id"]

        r3 = client.delete(
            "/inventory/delete-inventory",
            params={"items": "Doomed Item"},
            headers=_headers(fs_store_token),
        )
        assert r3.status_code == 200

        r4 = client.get("/flash-sales/store", headers=_headers(fs_store_token))
        assert r4.status_code == 200
        assert all(s["id"] != sale_id for s in r4.json())


class TestFlashSaleCartPricing:
    """A shopper adding a flash-sale item to their cart must be charged the
    sale price, and can't override it by sending a different `price` in the
    request body — the server derives price server-side, never trusting the
    client. Regression coverage for the bug where cart items were always
    added at the regular price, and for the price-tampering hole that let a
    client set any price it wanted."""

    def test_add_to_cart_uses_flash_sale_price_not_client_price(
        self, fs_store_token, fs_store_profile, promo_user_token, promo_user_profile
    ):
        r = client.post(
            "/inventory/add-inventory",
            json={"name": "Cart Pricing Item", "quantity": 20, "category": "OTHER", "price": 10.0},
            headers=_headers(fs_store_token),
        )
        assert r.status_code == 200, r.text
        inv_id = r.json()["inventory_id"]

        store_id = client.get("/stores/my-stores", headers=_headers(fs_store_token)).json()[0]["id"]

        now = datetime.utcnow()
        fs_payload = {
            "inventory_id": inv_id,
            "sale_price": 4.0,
            "start_at": (now - timedelta(minutes=1)).isoformat(),
            "end_at": (now + timedelta(hours=1)).isoformat(),
        }
        r2 = client.post("/flash-sales", json=fs_payload, headers=_headers(fs_store_token))
        assert r2.status_code == 200, r2.text

        # Client sends a bogus price far below even the sale price — server
        # must ignore it and use the real flash-sale price (4.0), not the
        # regular price (10.0) and not the client's number (0.01).
        r3 = client.post(
            f"/cart/{store_id}/items",
            json={"inventory_id": inv_id, "quantity": 2, "price": 0.01},
            headers=_headers(promo_user_token),
        )
        assert r3.status_code == 201, r3.text
        assert r3.json()["price"] == 4.0

        total = client.get(f"/cart/{store_id}/total", headers=_headers(promo_user_token)).json()
        assert total["total_price"] == 8.0  # 2 * 4.0, not 2 * 10.0 or 2 * 0.01

    def test_update_cart_item_cannot_override_price(
        self, fs_store_token, fs_store_profile, promo_user_token, promo_user_profile
    ):
        r = client.post(
            "/inventory/add-inventory",
            json={"name": "No Sale Item", "quantity": 20, "category": "OTHER", "price": 7.0},
            headers=_headers(fs_store_token),
        )
        assert r.status_code == 200, r.text
        inv_id = r.json()["inventory_id"]
        store_id = client.get("/stores/my-stores", headers=_headers(fs_store_token)).json()[0]["id"]

        r2 = client.post(
            f"/cart/{store_id}/items",
            json={"inventory_id": inv_id, "quantity": 1, "price": 7.0},
            headers=_headers(promo_user_token),
        )
        assert r2.status_code == 201, r2.text
        item_id = r2.json()["id"]

        r3 = client.put(
            f"/cart/{store_id}/items/{item_id}",
            json={"quantity": 3, "price": 0.01},
            headers=_headers(promo_user_token),
        )
        assert r3.status_code == 200, r3.text
        assert r3.json()["price"] == 7.0
        assert r3.json()["quantity"] == 3

    def test_browse_flash_sale_end_at_is_tz_aware(
        self, fs_store_token, fs_store_profile, promo_user_token, promo_user_profile
    ):
        """Regression test for the grocer/shopper countdown mismatch: the
        shopper-facing browse endpoint must serialize flash_sale_end_at with
        a UTC offset, same as /flash-sales/store, so both sides parse the
        same instant instead of one side misreading it as local time."""
        r = client.post(
            "/inventory/add-inventory",
            json={"name": "Browse Countdown Item", "quantity": 5, "category": "OTHER", "price": 12.0},
            headers=_headers(fs_store_token),
        )
        assert r.status_code == 200, r.text
        inv_id = r.json()["inventory_id"]
        store_id = client.get("/stores/my-stores", headers=_headers(fs_store_token)).json()[0]["id"]

        now = datetime.utcnow()
        fs_payload = {
            "inventory_id": inv_id,
            "sale_price": 6.0,
            "start_at": (now - timedelta(minutes=1)).isoformat(),
            "end_at": (now + timedelta(hours=1)).isoformat(),
        }
        r2 = client.post("/flash-sales", json=fs_payload, headers=_headers(fs_store_token))
        assert r2.status_code == 200, r2.text

        r3 = client.get(f"/inventory/browse/{store_id}", headers=_headers(promo_user_token))
        assert r3.status_code == 200, r3.text
        item = next(i for i in r3.json()["inventory"] if i["id"] == inv_id)
        assert item["flash_sale_price"] == 6.0
        assert item["flash_sale_end_at"].endswith("+00:00") or item["flash_sale_end_at"].endswith("Z")


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures: back-in-stock tests
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def bis_store_token():
    phone = _phone("12")
    _otp_and_verify(phone)
    _register(phone, "store")
    return _login(phone)


@pytest.fixture(scope="module")
def bis_store_profile(bis_store_token):
    r = client.post(
        "/user/set-profile",
        json={"name": "OOS Grocer", "email": "oosgrocer@groceror.test"},
        headers=_headers(bis_store_token),
    )
    assert r.status_code == 200, r.text
    return {"name": "OOS Grocer", "email": "oosgrocer@groceror.test"}


@pytest.fixture(scope="module")
def bis_oos_inventory_id(bis_store_token, bis_store_profile):
    r = client.post(
        "/inventory/add-inventory",
        json={"name": "Limited Cheese", "quantity": 0, "category": "DAIRY"},
        headers=_headers(bis_store_token),
    )
    assert r.status_code == 200, r.text
    return r.json()["inventory_id"]


@pytest.fixture(scope="module")
def bis_instock_inventory_id(bis_store_token, bis_store_profile):
    r = client.post(
        "/inventory/add-inventory",
        json={"name": "Plentiful Milk", "quantity": 10, "category": "DAIRY"},
        headers=_headers(bis_store_token),
    )
    assert r.status_code == 200, r.text
    return r.json()["inventory_id"]


@pytest.fixture(scope="module")
def bis_user_token():
    phone = _phone("13")
    _otp_and_verify(phone)
    _register(phone, "user")
    return _login(phone)


@pytest.fixture(scope="module")
def bis_user_profile(bis_user_token):
    r = client.post(
        "/user/set-profile",
        json={"name": "BIS User", "email": "bisuser@groceror.test"},
        headers=_headers(bis_user_token),
    )
    assert r.status_code == 200, r.text
    return {"name": "BIS User", "email": "bisuser@groceror.test"}


class TestBackInStock:

    def test_subscribe_requires_out_of_stock_item(
        self, bis_user_token, bis_user_profile, bis_instock_inventory_id
    ):
        r = client.post(f"/back-in-stock/{bis_instock_inventory_id}", headers=_headers(bis_user_token))
        assert r.status_code == 400
        assert "already in stock" in r.json()["detail"]

    def test_subscribe_item_not_found(self, bis_user_token, bis_user_profile):
        fake_id = str(uuid.uuid4())
        r = client.post(f"/back-in-stock/{fake_id}", headers=_headers(bis_user_token))
        assert r.status_code == 404
        assert r.json()["detail"] == "Item not found"

    def test_subscribe_requires_user_profile(self, bis_oos_inventory_id):
        phone = _phone("14")
        _otp_and_verify(phone)
        _register(phone, "store")  # registered but never calls set-profile -> no User row
        token = _login(phone)
        r = client.post(f"/back-in-stock/{bis_oos_inventory_id}", headers=_headers(token))
        assert r.status_code == 400
        assert r.json()["detail"] == "User profile not set"

    def test_subscribe_creates_alert(self, bis_user_token, bis_user_profile, bis_oos_inventory_id, bis_store_profile):
        r = client.post(f"/back-in-stock/{bis_oos_inventory_id}", headers=_headers(bis_user_token))
        assert r.status_code == 200
        data = r.json()
        assert data["inventory_id"] == bis_oos_inventory_id
        assert data["inventory_name"] == "Limited Cheese"
        assert data["store_name"] == bis_store_profile["name"]
        assert data["current_stock"] == 0
        assert data["is_triggered"] is False
        assert data["triggered_at"] is None

    def test_subscribe_again_returns_existing_alert_idempotently(
        self, bis_user_token, bis_user_profile, bis_oos_inventory_id
    ):
        r = client.post(f"/back-in-stock/{bis_oos_inventory_id}", headers=_headers(bis_user_token))
        assert r.status_code == 200

        r2 = client.get("/back-in-stock", headers=_headers(bis_user_token))
        assert r2.status_code == 200
        matches = [a for a in r2.json() if a["inventory_id"] == bis_oos_inventory_id]
        assert len(matches) == 1

    def test_list_alerts(self, bis_user_token, bis_user_profile, bis_oos_inventory_id):
        r = client.get("/back-in-stock", headers=_headers(bis_user_token))
        assert r.status_code == 200
        assert any(a["inventory_id"] == bis_oos_inventory_id for a in r.json())

    def test_restock_triggers_alert(
        self, bis_user_token, bis_user_profile, bis_store_token, bis_oos_inventory_id
    ):
        r = client.put(
            f"/inventory/{bis_oos_inventory_id}",
            json={"quantity": 5},
            headers=_headers(bis_store_token),
        )
        assert r.status_code == 200, r.text

        r2 = client.get("/back-in-stock", headers=_headers(bis_user_token))
        assert r2.status_code == 200
        alert = next(a for a in r2.json() if a["inventory_id"] == bis_oos_inventory_id)
        assert alert["is_triggered"] is True
        assert alert["triggered_at"] is not None
        assert alert["current_stock"] == 5

    def test_unsubscribe(self, bis_user_token, bis_user_profile, bis_oos_inventory_id):
        r = client.delete(f"/back-in-stock/{bis_oos_inventory_id}", headers=_headers(bis_user_token))
        assert r.status_code == 204

        r2 = client.get("/back-in-stock", headers=_headers(bis_user_token))
        assert not any(a["inventory_id"] == bis_oos_inventory_id for a in r2.json())

    def test_unsubscribe_nonexistent_is_a_noop(self, bis_user_token, bis_user_profile):
        fake_id = str(uuid.uuid4())
        r = client.delete(f"/back-in-stock/{fake_id}", headers=_headers(bis_user_token))
        assert r.status_code == 204
