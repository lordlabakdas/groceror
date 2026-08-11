"""
Integration tests for bulk pricing rules, coupons, and delivery zones.

Covers:
  - api/bulk_rule_api.py    (BXGF + bundle rule CRUD, and apply_bulk_rules()
                              via real order creation)
  - api/coupon_api.py       (coupon CRUD, /available listing, /validate)
  - api/delivery_zone_api.py (zone CRUD, /store/{id} lookup, /nearby search)

These three routers all gate store-only endpoints behind an identical
`_get_store` dependency (403 for non-store accounts, 400 when the store
entity has never called POST /stores/). Because store accounts are looked
up via `Store.entity_id == entity.id` with no `.order_by()`, and the shared
conftest.py `store_token`/`store_id` fixtures are reused (and re-POST
new Store rows) across every test module in the suite, relying on them here
would make `_get_store()`'s `.first()` resolution ambiguous once the full
suite runs together. To keep every assertion deterministic, this file
creates its own dedicated store accounts (store_a, store_b, store_c) on
fresh phone numbers instead of depending on the shared store_token/store_id
fixtures. The shared `user_token`/`user_profile` fixtures are reused freely
since User profiles are upserted (one row per entity, never duplicated).
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

# Per-run unique phone suffix, independent from helpers.py's own _suffix, so
# this file never collides with the other agents' new test files even when
# the full suite runs together.
_suffix = str(uuid.uuid4().int)[:6]


# ─────────────────────────────────────────────────────────────────────────────
# Local helpers
# ─────────────────────────────────────────────────────────────────────────────

def _new_store_account(tag: str) -> str:
    """Registers+logs in a fresh store-type entity. Does NOT create a Store row."""
    phone = f"+1559{_suffix}{tag}"
    _otp_and_verify(phone)
    _register(phone, "store")
    return _login(phone)


def _create_store_row(token: str, name: str, email: str) -> str:
    r = client.post(
        "/stores/",
        json={"name": name, "email": email, "location": "Test Location"},
        headers=_headers(token),
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _add_inventory(token: str, name: str, price: float, quantity: int = 50, category: str = "GROCERY") -> str:
    r = client.post(
        "/inventory/add-inventory",
        json={"name": name, "quantity": quantity, "category": category, "price": price},
        headers=_headers(token),
    )
    assert r.status_code == 200, r.text
    return r.json()["inventory_id"]


def _create_coupon(token: str, code: str, discount_type: str, discount_value: float, **extra) -> dict:
    payload = {"code": code, "discount_type": discount_type, "discount_value": discount_value}
    payload.update(extra)
    r = client.post("/coupons", json=payload, headers=_headers(token))
    assert r.status_code == 201, r.text
    return r.json()


# ─────────────────────────────────────────────────────────────────────────────
# Module-scoped fixtures (private to this file)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def store_a():
    """Primary store used for the bulk of the happy-path scenarios."""
    token = _new_store_account("01")
    store_id = _create_store_row(token, "Bulk Zone Store A", f"storea{_suffix}@groceror.test")
    return {"token": token, "id": store_id}


@pytest.fixture(scope="module")
def store_b():
    """A second, unrelated store used for cross-store ownership checks."""
    token = _new_store_account("02")
    store_id = _create_store_row(token, "Bulk Zone Store B", f"storeb{_suffix}@groceror.test")
    return {"token": token, "id": store_id}


@pytest.fixture(scope="module")
def store_c_token():
    """A store-type entity that never calls POST /stores/ (400 branch)."""
    return _new_store_account("03")


@pytest.fixture(scope="module")
def bulk_items(store_a):
    return {
        "bxgf": _add_inventory(store_a["token"], "BXGFItem", price=2.0, quantity=100),
        "pct_a": _add_inventory(store_a["token"], "PctItemA", price=5.0, quantity=50),
        "pct_b": _add_inventory(store_a["token"], "PctItemB", price=3.0, quantity=50),
        "fixed_a": _add_inventory(store_a["token"], "FixedItemA", price=6.0, quantity=50),
        "fixed_b": _add_inventory(store_a["token"], "FixedItemB", price=4.0, quantity=50),
    }


@pytest.fixture(scope="module")
def bulk_rules(store_a, bulk_items):
    """Creates one active BXGF rule and two active bundle rules (percent + fixed)."""
    bxgf = client.post(
        "/bulk-rules/bxgf",
        json={"name": "Buy 2 Get 1", "inventory_id": bulk_items["bxgf"], "buy_quantity": 2, "free_quantity": 1},
        headers=_headers(store_a["token"]),
    )
    assert bxgf.status_code == 200, bxgf.text

    pct = client.post(
        "/bulk-rules/bundle",
        json={
            "name": "Combo Percent",
            "inventory_ids": [bulk_items["pct_a"], bulk_items["pct_b"]],
            "discount_type": "percent",
            "discount_value": 20,
        },
        headers=_headers(store_a["token"]),
    )
    assert pct.status_code == 200, pct.text

    fixed = client.post(
        "/bulk-rules/bundle",
        json={
            "name": "Combo Fixed",
            "inventory_ids": [bulk_items["fixed_a"], bulk_items["fixed_b"]],
            "discount_type": "fixed",
            "discount_value": 5,
        },
        headers=_headers(store_a["token"]),
    )
    assert fixed.status_code == 200, fixed.text

    return {"bxgf": bxgf.json(), "pct": pct.json(), "fixed": fixed.json()}


@pytest.fixture(scope="module")
def coupon_codes():
    return {k: f"CPN{_suffix}{k}" for k in ["A", "B", "C", "D", "E", "F", "G", "I"]}


@pytest.fixture(scope="module")
def coupons(store_a, coupon_codes):
    today = date.today()
    c = coupon_codes
    return {
        "A": _create_coupon(store_a["token"], c["A"], "percent", 10),
        "B": _create_coupon(store_a["token"], c["B"], "fixed", 5),
        "C": _create_coupon(store_a["token"], c["C"], "percent", 15),
        "D": _create_coupon(
            store_a["token"], c["D"], "fixed", 5,
            valid_until=(today - timedelta(days=1)).isoformat(),
        ),
        "E": _create_coupon(
            store_a["token"], c["E"], "percent", 15,
            valid_from=(today + timedelta(days=1)).isoformat(),
        ),
        "F": _create_coupon(store_a["token"], c["F"], "fixed", 5, max_uses=0),
        "G": _create_coupon(store_a["token"], c["G"], "percent", 10, min_order_amount=50),
        "I": _create_coupon(store_a["token"], c["I"], "percent", 10),
    }


# ─────────────────────────────────────────────────────────────────────────────
# BULK RULES
# ─────────────────────────────────────────────────────────────────────────────

class TestBulkRuleAuth:
    """_get_store() guard (api/bulk_rule_api.py:21-27) plus the 404 inventory
    branches inside create_bxgf/create_bundle (lines 101-118, 123-145)."""

    def test_bxgf_requires_store_role(self, user_token):
        r = client.post(
            "/bulk-rules/bxgf",
            json={"name": "x", "inventory_id": str(uuid.uuid4()), "buy_quantity": 1, "free_quantity": 1},
            headers=_headers(user_token),
        )
        assert r.status_code == 403
        assert "Store access only" in r.json()["detail"]

    def test_bxgf_requires_store_profile(self, store_c_token):
        r = client.post(
            "/bulk-rules/bxgf",
            json={"name": "x", "inventory_id": str(uuid.uuid4()), "buy_quantity": 1, "free_quantity": 1},
            headers=_headers(store_c_token),
        )
        assert r.status_code == 400
        assert "Store profile not set" in r.json()["detail"]

    def test_create_bxgf_inventory_not_found(self, store_a):
        r = client.post(
            "/bulk-rules/bxgf",
            json={"name": "Ghost Rule", "inventory_id": str(uuid.uuid4()), "buy_quantity": 2, "free_quantity": 1},
            headers=_headers(store_a["token"]),
        )
        assert r.status_code == 404
        assert "not found in your store" in r.json()["detail"]

    def test_create_bundle_inventory_not_found(self, store_a, bulk_items):
        r = client.post(
            "/bulk-rules/bundle",
            json={
                "name": "Bad Bundle",
                "inventory_ids": [bulk_items["pct_a"], str(uuid.uuid4())],
                "discount_type": "percent",
                "discount_value": 10,
            },
            headers=_headers(store_a["token"]),
        )
        assert r.status_code == 404
        assert "not found in your store" in r.json()["detail"]


class TestBulkRuleCRUD:
    """Happy-path create/list/deactivate flows."""

    def test_create_bxgf_rule_response_shape(self, bulk_rules, bulk_items):
        data = bulk_rules["bxgf"]
        assert data["rule_type"] == "bxgf"
        assert data["bxgf_inventory_id"] == bulk_items["bxgf"]
        assert data["bxgf_inventory_name"] == "BXGFItem"
        assert data["buy_quantity"] == 2
        assert data["free_quantity"] == 1
        assert data["is_active"] is True
        assert data["bundle_items"] == []

    def test_create_bundle_rule_response_shape(self, bulk_rules, bulk_items):
        data = bulk_rules["pct"]
        assert data["rule_type"] == "bundle"
        assert data["discount_type"] == "percent"
        assert data["discount_value"] == 20
        assert len(data["bundle_items"]) == 2
        names = {bi["name"] for bi in data["bundle_items"]}
        assert names == {"PctItemA", "PctItemB"}

    def test_list_my_rules(self, store_a, bulk_rules):
        r = client.get("/bulk-rules", headers=_headers(store_a["token"]))
        assert r.status_code == 200
        data = r.json()
        ids = {d["id"] for d in data}
        assert bulk_rules["bxgf"]["id"] in ids
        assert bulk_rules["pct"]["id"] in ids
        assert bulk_rules["fixed"]["id"] in ids

    def test_list_store_rules_public(self, store_a, bulk_rules):
        r = client.get(f"/bulk-rules/store/{store_a['id']}")
        assert r.status_code == 200
        ids = {d["id"] for d in r.json()}
        assert bulk_rules["bxgf"]["id"] in ids

    def test_list_store_rules_unknown_store(self):
        r = client.get(f"/bulk-rules/store/{uuid.uuid4()}")
        assert r.status_code == 200
        assert r.json() == []

    def test_deactivate_rule_not_found(self, store_a):
        r = client.delete(f"/bulk-rules/{uuid.uuid4()}", headers=_headers(store_a["token"]))
        assert r.status_code == 404
        assert "Rule not found" in r.json()["detail"]

    def test_deactivate_rule_flow(self, store_a, store_b):
        """Self-contained: create a disposable rule, confirm cross-store
        deactivation is a 404 (not 403), then deactivate it for real."""
        disposable_item = _add_inventory(store_a["token"], "DisposableItem", price=1.0, quantity=20)
        r = client.post(
            "/bulk-rules/bxgf",
            json={"name": "Disposable Rule", "inventory_id": disposable_item, "buy_quantity": 1, "free_quantity": 1},
            headers=_headers(store_a["token"]),
        )
        assert r.status_code == 200, r.text
        rule_id = r.json()["id"]

        # store_b doesn't own this rule -> scoped query finds nothing -> 404
        r = client.delete(f"/bulk-rules/{rule_id}", headers=_headers(store_b["token"]))
        assert r.status_code == 404

        r = client.delete(f"/bulk-rules/{rule_id}", headers=_headers(store_a["token"]))
        assert r.status_code == 204

        ids = [d["id"] for d in client.get("/bulk-rules", headers=_headers(store_a["token"])).json()]
        assert rule_id not in ids


class TestBulkRuleOrderDiscounts:
    """Exercises apply_bulk_rules() (api/bulk_rule_api.py:177-212) via real
    order creation -- this function is only reachable through OrderService,
    it has no direct HTTP endpoint of its own."""

    @patch("engine.mailer.Mailer.send")
    def test_bxgf_discount_applied(self, mock_send, user_token, user_profile, bulk_items, bulk_rules):
        # buy_quantity=2, free_quantity=1, price=2.0; qty=3 -> 1 free unit -> $2.00 off
        r = client.post(
            "/order/create-order",
            json={"items": [{"inventory_id": bulk_items["bxgf"], "quantity": 3}]},
            headers=_headers(user_token),
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["discount_amount"] == pytest.approx(2.0)
        assert data["total_price"] == pytest.approx(4.0)

    @patch("engine.mailer.Mailer.send")
    def test_bundle_percent_discount_applied(self, mock_send, user_token, user_profile, bulk_items, bulk_rules):
        # 1x $5.00 + 1x $3.00 = $8.00 subtotal, 20% off -> $1.60 off
        r = client.post(
            "/order/create-order",
            json={
                "items": [
                    {"inventory_id": bulk_items["pct_a"], "quantity": 1},
                    {"inventory_id": bulk_items["pct_b"], "quantity": 1},
                ]
            },
            headers=_headers(user_token),
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["discount_amount"] == pytest.approx(1.6)
        assert data["total_price"] == pytest.approx(6.4)

    @patch("engine.mailer.Mailer.send")
    def test_bundle_fixed_discount_applied(self, mock_send, user_token, user_profile, bulk_items, bulk_rules):
        # 1x $6.00 + 1x $4.00 = $10.00 subtotal, fixed $5.00 off (below subtotal, no cap)
        r = client.post(
            "/order/create-order",
            json={
                "items": [
                    {"inventory_id": bulk_items["fixed_a"], "quantity": 1},
                    {"inventory_id": bulk_items["fixed_b"], "quantity": 1},
                ]
            },
            headers=_headers(user_token),
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["discount_amount"] == pytest.approx(5.0)
        assert data["total_price"] == pytest.approx(5.0)

    @patch("engine.mailer.Mailer.send")
    def test_bundle_discount_not_applied_when_only_partial_items_ordered(
        self, mock_send, user_token, user_profile, bulk_items, bulk_rules
    ):
        """Ordering only ONE of the two bundled items should not trigger the
        bundle discount (bundle_ids.issubset(qty_map.keys()) is False)."""
        r = client.post(
            "/order/create-order",
            json={"items": [{"inventory_id": bulk_items["pct_a"], "quantity": 1}]},
            headers=_headers(user_token),
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["discount_amount"] == pytest.approx(0.0)
        assert data["total_price"] == pytest.approx(5.0)


# ─────────────────────────────────────────────────────────────────────────────
# COUPONS
# ─────────────────────────────────────────────────────────────────────────────

class TestCoupons:
    """Coupon CRUD: create validation branches, list, deactivate."""

    def test_create_coupon_requires_store_role(self, user_token):
        r = client.post(
            "/coupons",
            json={"code": "X", "discount_type": "percent", "discount_value": 5},
            headers=_headers(user_token),
        )
        assert r.status_code == 403
        assert "Store access only" in r.json()["detail"]

    def test_create_coupon_requires_store_profile(self, store_c_token):
        r = client.post(
            "/coupons",
            json={"code": "X", "discount_type": "percent", "discount_value": 5},
            headers=_headers(store_c_token),
        )
        assert r.status_code == 400
        assert "Store profile not set" in r.json()["detail"]

    def test_create_coupon_uppercases_and_defaults(self, coupons, coupon_codes):
        a = coupons["A"]
        assert a["code"] == coupon_codes["A"].upper()
        assert a["discount_type"] == "percent"
        assert a["discount_value"] == 10
        assert a["uses_count"] == 0
        assert a["is_active"] is True

    def test_create_coupon_empty_code(self, store_a):
        r = client.post(
            "/coupons",
            json={"code": "   ", "discount_type": "percent", "discount_value": 5},
            headers=_headers(store_a["token"]),
        )
        assert r.status_code == 400
        assert "cannot be empty" in r.json()["detail"]

    def test_create_coupon_invalid_date_range(self, store_a):
        today = date.today()
        r = client.post(
            "/coupons",
            json={
                "code": f"BADDATE{_suffix}",
                "discount_type": "fixed",
                "discount_value": 5,
                "valid_from": (today + timedelta(days=5)).isoformat(),
                "valid_until": today.isoformat(),
            },
            headers=_headers(store_a["token"]),
        )
        assert r.status_code == 400
        assert "valid_from must be before valid_until" in r.json()["detail"]

    def test_create_coupon_percent_over_100(self, store_a):
        r = client.post(
            "/coupons",
            json={"code": f"OVER{_suffix}", "discount_type": "percent", "discount_value": 150},
            headers=_headers(store_a["token"]),
        )
        assert r.status_code == 400
        assert "cannot exceed 100" in r.json()["detail"]

    def test_create_coupon_duplicate_code(self, store_a, coupons, coupon_codes):
        r = client.post(
            "/coupons",
            json={"code": coupon_codes["A"], "discount_type": "fixed", "discount_value": 1},
            headers=_headers(store_a["token"]),
        )
        assert r.status_code == 409
        assert "already exists" in r.json()["detail"]

    def test_list_coupons(self, store_a, coupons, coupon_codes):
        r = client.get("/coupons", headers=_headers(store_a["token"]))
        assert r.status_code == 200
        codes = {c["code"] for c in r.json()}
        assert coupon_codes["A"] in codes
        assert coupon_codes["B"] in codes

    def test_deactivate_coupon_not_found(self, store_a):
        r = client.delete(f"/coupons/NOPE{_suffix}", headers=_headers(store_a["token"]))
        assert r.status_code == 404
        assert "Coupon not found" in r.json()["detail"]

    def test_deactivate_coupon_cross_store_not_found(self, store_b, coupons, coupon_codes):
        r = client.delete(f"/coupons/{coupon_codes['C']}", headers=_headers(store_b["token"]))
        assert r.status_code == 404

    def test_deactivate_coupon(self, store_a, coupons, coupon_codes):
        r = client.delete(f"/coupons/{coupon_codes['A']}", headers=_headers(store_a["token"]))
        assert r.status_code == 204

        r = client.get("/coupons", headers=_headers(store_a["token"]))
        a = next(c for c in r.json() if c["code"] == coupon_codes["A"])
        assert a["is_active"] is False


class TestCouponAvailability:
    """GET /coupons/available (api/coupon_api.py:112-127)."""

    def test_list_available_filters_correctly(self, store_a, user_token, coupons, coupon_codes):
        r = client.get("/coupons/available", params={"store_id": store_a["id"]}, headers=_headers(user_token))
        assert r.status_code == 200
        codes = {c["code"] for c in r.json()}
        assert coupon_codes["B"] in codes  # active, unrestricted
        assert coupon_codes["I"] in codes  # active, unrestricted
        assert coupon_codes["A"] not in codes  # deactivated
        assert coupon_codes["D"] not in codes  # expired
        assert coupon_codes["E"] not in codes  # not yet active
        assert coupon_codes["F"] not in codes  # max_uses == uses_count == 0

    def test_list_available_requires_auth(self, store_a):
        r = client.get("/coupons/available", params={"store_id": store_a["id"]})
        assert r.status_code == 401


class TestCouponValidate:
    """GET /coupons/{code}/validate (api/coupon_api.py:130-172)."""

    def test_validate_unknown_code(self, user_token):
        r = client.get(f"/coupons/NOSUCHCODE{_suffix}/validate", headers=_headers(user_token))
        assert r.status_code == 200
        data = r.json()
        assert data["valid"] is False
        assert data["message"] == "Coupon not found or inactive"
        assert data["discount_amount"] == 0

    def test_validate_inactive_code(self, user_token, coupons, coupon_codes):
        r = client.get(f"/coupons/{coupon_codes['A']}/validate", headers=_headers(user_token))
        assert r.status_code == 200
        data = r.json()
        assert data["valid"] is False
        assert data["message"] == "Coupon not found or inactive"

    def test_validate_not_yet_active(self, user_token, coupons, coupon_codes):
        r = client.get(f"/coupons/{coupon_codes['E']}/validate", headers=_headers(user_token))
        data = r.json()
        assert data["valid"] is False
        assert data["message"] == "Coupon is not yet active"

    def test_validate_expired(self, user_token, coupons, coupon_codes):
        r = client.get(f"/coupons/{coupon_codes['D']}/validate", headers=_headers(user_token))
        data = r.json()
        assert data["valid"] is False
        assert data["message"] == "Coupon has expired"

    def test_validate_usage_limit_reached(self, user_token, coupons, coupon_codes):
        r = client.get(f"/coupons/{coupon_codes['F']}/validate", headers=_headers(user_token))
        data = r.json()
        assert data["valid"] is False
        assert data["message"] == "Coupon has reached its usage limit"

    def test_validate_min_order_not_met(self, user_token, coupons, coupon_codes):
        r = client.get(
            f"/coupons/{coupon_codes['G']}/validate", params={"order_total": 10}, headers=_headers(user_token)
        )
        data = r.json()
        assert data["valid"] is False
        assert data["message"] == "Minimum order of $50.00 required"

    def test_validate_success_percent(self, user_token, coupons, coupon_codes):
        r = client.get(
            f"/coupons/{coupon_codes['I']}/validate", params={"order_total": 100}, headers=_headers(user_token)
        )
        data = r.json()
        assert data["valid"] is True
        assert data["discount_amount"] == pytest.approx(10.0)
        assert "saves $10.00" in data["message"]

    def test_validate_success_fixed_uncapped(self, user_token, coupons, coupon_codes):
        r = client.get(
            f"/coupons/{coupon_codes['B']}/validate", params={"order_total": 100}, headers=_headers(user_token)
        )
        data = r.json()
        assert data["valid"] is True
        assert data["discount_amount"] == pytest.approx(5.0)

    def test_validate_success_fixed_capped_by_order_total(self, user_token, coupons, coupon_codes):
        r = client.get(
            f"/coupons/{coupon_codes['B']}/validate", params={"order_total": 2}, headers=_headers(user_token)
        )
        data = r.json()
        assert data["valid"] is True
        assert data["discount_amount"] == pytest.approx(2.0)

    def test_validate_defaults_order_total_to_zero(self, user_token, coupons, coupon_codes):
        """order_total query param has a default of 0.0."""
        r = client.get(f"/coupons/{coupon_codes['I']}/validate", headers=_headers(user_token))
        assert r.status_code == 200
        data = r.json()
        assert data["valid"] is True
        assert data["discount_amount"] == pytest.approx(0.0)

    def test_validate_requires_auth(self, coupons, coupon_codes):
        r = client.get(f"/coupons/{coupon_codes['B']}/validate")
        assert r.status_code == 401


# ─────────────────────────────────────────────────────────────────────────────
# DELIVERY ZONES
# ─────────────────────────────────────────────────────────────────────────────

class TestDeliveryZones:
    """Ordered flow: create -> get -> update -> nearby -> remove -> remove again."""

    def test_set_zone_requires_store_role(self, user_token):
        r = client.put(
            "/delivery-zones",
            json={"latitude": 40.0, "longitude": -73.0, "radius_km": 5},
            headers=_headers(user_token),
        )
        assert r.status_code == 403
        assert "Store access only" in r.json()["detail"]

    def test_set_zone_requires_store_profile(self, store_c_token):
        r = client.put(
            "/delivery-zones",
            json={"latitude": 40.0, "longitude": -73.0, "radius_km": 5},
            headers=_headers(store_c_token),
        )
        assert r.status_code == 400
        assert "Store profile not set" in r.json()["detail"]

    def test_create_zone(self, store_a):
        r = client.put(
            "/delivery-zones",
            json={"latitude": 40.7128, "longitude": -74.0060, "radius_km": 10},
            headers=_headers(store_a["token"]),
        )
        assert r.status_code == 200
        data = r.json()
        assert data["store_id"] == store_a["id"]
        assert data["latitude"] == pytest.approx(40.7128)
        assert data["longitude"] == pytest.approx(-74.0060)
        assert data["radius_km"] == pytest.approx(10)

    def test_get_zone_by_store(self, store_a):
        r = client.get(f"/delivery-zones/store/{store_a['id']}")
        assert r.status_code == 200
        assert r.json()["store_id"] == store_a["id"]

    def test_get_zone_for_store_without_zone(self, store_b):
        r = client.get(f"/delivery-zones/store/{store_b['id']}")
        assert r.status_code == 200
        assert r.json() is None

    def test_update_zone(self, store_a):
        """PUT again on an existing zone hits the update branch, not create."""
        r = client.put(
            "/delivery-zones",
            json={"latitude": 41.0, "longitude": -75.0, "radius_km": 20},
            headers=_headers(store_a["token"]),
        )
        assert r.status_code == 200
        data = r.json()
        assert data["store_id"] == store_a["id"]
        assert data["latitude"] == pytest.approx(41.0)
        assert data["radius_km"] == pytest.approx(20)

        # Confirm it's still a single zone row for this store, not a second one.
        r = client.get(f"/delivery-zones/store/{store_a['id']}")
        assert r.json()["latitude"] == pytest.approx(41.0)

    def test_nearby_stores_includes_match(self, store_a):
        r = client.get("/delivery-zones/nearby", params={"lat": 41.0, "lng": -75.0})
        assert r.status_code == 200
        matches = [z for z in r.json() if z["store_id"] == store_a["id"]]
        assert len(matches) == 1
        assert matches[0]["distance_km"] == pytest.approx(0.0, abs=0.01)
        assert matches[0]["store_name"] == "Bulk Zone Store A"

    def test_nearby_stores_excludes_out_of_range(self, store_a):
        # Sydney, AU is nowhere near store_a's 20km zone around (41, -75).
        r = client.get("/delivery-zones/nearby", params={"lat": -33.8688, "lng": 151.2093})
        assert r.status_code == 200
        assert all(z["store_id"] != store_a["id"] for z in r.json())

    def test_remove_zone(self, store_a):
        r = client.delete("/delivery-zones", headers=_headers(store_a["token"]))
        assert r.status_code == 204

    def test_remove_zone_not_found(self, store_a):
        """Zone was already removed by the previous test -> 404 branch."""
        r = client.delete("/delivery-zones", headers=_headers(store_a["token"]))
        assert r.status_code == 404
        assert "No delivery zone configured" in r.json()["detail"]
