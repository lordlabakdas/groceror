"""
Integration tests for inventory, dashboard, and product endpoints.

Targets (per `pytest --cov` gaps at the time this file was written):
  - api/inventory_api.py       (add/get/delete 500 branches, threshold, expiry,
                                 promotion set/delete, update, search, browse, trending)
  - api/dashboard_api.py       (403 branch, low-stock branches, expiring-soon
                                 dedup, top-sellers cap, revenue-trend)
  - api/product_api.py         (list/filter/search, get 404, add incl. 409 conflict)
  - api/helpers/inventory_helper.py (exercised indirectly through the endpoints
                                 above — items filter, price-on-reorder, expiry/
                                 promo enrichment, low-stock + back-in-stock
                                 trigger branches inside update_inventory_fields)

Each test spins up its own store/user account (unique phone number per test
run) rather than relying on the shared module-scoped fixtures in conftest.py,
so that store->inventory correspondence is fully deterministic regardless of
what other integration test files do in the same pytest session (conftest's
`InventoryHelper._require_store()` resolves the *first* Store row for a given
entity_id, and the shared fixtures reuse the same phone number/entity across
every test file that imports them — creating our own accounts sidesteps that
entirely).
"""
import itertools
import uuid
from datetime import date, datetime, timedelta
from unittest.mock import patch

from tests.integration.helpers import (
    _headers,
    _login,
    _otp_and_verify,
    _register,
    client,
)

_suffix = str(uuid.uuid4().int)[:6]
_tag_counter = itertools.count(1)


def _unique_phone() -> str:
    return f"+1557{_suffix}{next(_tag_counter):04d}"


def _n(base: str) -> str:
    """Globally-unique name for inventory/product rows created in this file."""
    return f"{base}-{_suffix}-{next(_tag_counter)}"


def _new_store_account(hint: str = "store") -> str:
    """Register + log in a fresh store-type account with a store profile set
    (so InventoryHelper._require_store() resolves it)."""
    phone = _unique_phone()
    _otp_and_verify(phone)
    _register(phone, "store")
    token = _login(phone)
    r = client.post(
        "/user/set-profile",
        json={
            "name": _n(hint),
            "email": f"{hint}{phone[-6:]}@groceror.test",
            "website": "https://example.test",
            # location intentionally omitted: set_store_profile geocodes it via
            # a live network call, which we don't want in tests.
        },
        headers=_headers(token),
    )
    assert r.status_code == 200, r.text
    return token


def _new_user_account(hint: str = "user") -> str:
    """Register + log in a fresh user-type account with a user profile set."""
    phone = _unique_phone()
    _otp_and_verify(phone)
    _register(phone, "user")
    token = _login(phone)
    r = client.post(
        "/user/set-profile",
        json={"name": _n(hint), "email": f"{hint}{phone[-6:]}@groceror.test"},
        headers=_headers(token),
    )
    assert r.status_code == 200, r.text
    return token


def _add_item(token: str, name: str, quantity: int, category: str = "OTHER", price: float = 0.0) -> str:
    r = client.post(
        "/inventory/add-inventory",
        json={"name": name, "quantity": quantity, "category": category, "price": price},
        headers=_headers(token),
    )
    assert r.status_code == 200, r.text
    return r.json()["inventory_id"]


# ─────────────────────────────────────────────────────────────────────────────
# PRODUCT CATALOG (api/product_api.py)
# ─────────────────────────────────────────────────────────────────────────────

class TestProducts:

    def test_add_product_requires_auth(self):
        r = client.post("/products", json={"name": _n("Widget"), "category": "OTHER"})
        assert r.status_code == 401

    def test_add_product_and_get(self):
        token = _new_user_account("prod")
        name = _n("TestProduct")
        r = client.post(
            "/products",
            json={"name": name, "category": "GROCERY", "default_price": 4.5, "image_url": "http://img.test/x.png"},
            headers=_headers(token),
        )
        assert r.status_code == 201, r.text
        product_id = r.json()["product_id"]
        uuid.UUID(product_id)  # valid UUID

        r2 = client.get(f"/products/{product_id}")
        assert r2.status_code == 200
        data = r2.json()
        assert data["name"] == name
        assert data["category"] == "GROCERY"
        assert data["default_price"] == 4.5
        assert data["image_url"] == "http://img.test/x.png"

    def test_add_product_duplicate_name_conflict(self):
        token = _new_user_account("prod")
        name = _n("DupProduct")
        payload = {"name": name, "category": "DAIRY", "default_price": 1.0}
        r1 = client.post("/products", json=payload, headers=_headers(token))
        assert r1.status_code == 201
        r2 = client.post("/products", json=payload, headers=_headers(token))
        assert r2.status_code == 409
        assert name in r2.json()["detail"]

    def test_get_nonexistent_product(self):
        fake_id = str(uuid.uuid4())
        r = client.get(f"/products/{fake_id}")
        assert r.status_code == 404
        assert r.json()["detail"] == "Product not found"

    def test_list_products_filter_by_category(self):
        token = _new_user_account("prod")
        name = _n("CatFilterProduct")
        client.post(
            "/products",
            json={"name": name, "category": "BAKERY", "default_price": 2.0},
            headers=_headers(token),
        )
        r = client.get("/products", params={"category": "BAKERY"})
        assert r.status_code == 200
        names = [p["name"] for p in r.json()["products"]]
        assert name in names
        # sanity: category filter actually filters (no MEAT products with this name)
        r2 = client.get("/products", params={"category": "MEAT"})
        assert name not in [p["name"] for p in r2.json()["products"]]

    def test_list_products_search_query(self):
        token = _new_user_account("prod")
        name = _n("SearchMeProduct")
        client.post(
            "/products",
            json={"name": name, "category": "MEAT", "default_price": 9.0},
            headers=_headers(token),
        )
        r = client.get("/products", params={"q": name[:10]})
        assert r.status_code == 200
        names = [p["name"] for p in r.json()["products"]]
        assert name in names

    def test_list_products_no_filters_returns_ok(self):
        r = client.get("/products")
        assert r.status_code == 200
        assert isinstance(r.json()["products"], list)

    def test_list_products_query_too_short_rejected(self):
        r = client.get("/products", params={"q": "a"})
        assert r.status_code == 422


# ─────────────────────────────────────────────────────────────────────────────
# INVENTORY: add / get / delete — 500 error branches (no-store account)
# ─────────────────────────────────────────────────────────────────────────────

class TestInventoryNoStoreErrorBranches:
    """These endpoints wrap InventoryHelper calls in a broad `except Exception`,
    so a caller with no Store row (helper._require_store() raises ValueError)
    surfaces as a 500, not a 403 — that's the actual behavior of the code."""

    def test_add_inventory_without_store_returns_500(self):
        token = _new_user_account("nostore")
        r = client.post(
            "/inventory/add-inventory",
            json={"name": _n("Ghost"), "quantity": 1, "category": "OTHER"},
            headers=_headers(token),
        )
        assert r.status_code == 500
        assert "Issue with registering user" in r.json()["detail"]

    def test_get_store_inventory_without_store_returns_500(self):
        token = _new_user_account("nostore")
        r = client.get("/inventory/get-store-inventory", headers=_headers(token))
        assert r.status_code == 500
        assert "Issue with retreiving store inventory" in r.json()["detail"]

    def test_delete_inventory_without_store_returns_500(self):
        token = _new_user_account("nostore")
        r = client.delete("/inventory/delete-inventory", headers=_headers(token))
        assert r.status_code == 500
        assert "Issue with deleting inventory" in r.json()["detail"]

    def test_inventory_add_invalid_category_rejected(self):
        token = _new_store_account("catcheck")
        r = client.post(
            "/inventory/add-inventory",
            json={"name": _n("Mystery"), "quantity": 1, "category": "NOT_A_CATEGORY"},
            headers=_headers(token),
        )
        assert r.status_code == 422


# ─────────────────────────────────────────────────────────────────────────────
# INVENTORY: add-inventory happy path — price update on reorder
# ─────────────────────────────────────────────────────────────────────────────

class TestInventoryAddReorder:

    def test_add_inventory_updates_price_when_reordering(self):
        token = _new_store_account("reorder")
        name = _n("PriceItem")
        client.post(
            "/inventory/add-inventory",
            json={"name": name, "quantity": 5, "category": "OTHER", "price": 1.0},
            headers=_headers(token),
        )
        r = client.post(
            "/inventory/add-inventory",
            json={"name": name, "quantity": 3, "category": "OTHER", "price": 9.99},
            headers=_headers(token),
        )
        assert r.status_code == 200

        inv = client.get("/inventory/get-store-inventory", headers=_headers(token)).json()["inventory"]
        item = next(i for i in inv if i["name"] == name)
        assert item["quantity"] == 8
        assert item["price"] == 9.99

    def test_add_inventory_zero_price_does_not_overwrite(self):
        token = _new_store_account("reorder")
        name = _n("KeepPriceItem")
        client.post(
            "/inventory/add-inventory",
            json={"name": name, "quantity": 5, "category": "OTHER", "price": 4.25},
            headers=_headers(token),
        )
        # Re-order without specifying a price (defaults to 0.0) — price must be unchanged.
        r = client.post(
            "/inventory/add-inventory",
            json={"name": name, "quantity": 2, "category": "OTHER"},
            headers=_headers(token),
        )
        assert r.status_code == 200
        inv = client.get("/inventory/get-store-inventory", headers=_headers(token)).json()["inventory"]
        item = next(i for i in inv if i["name"] == name)
        assert item["quantity"] == 7
        assert item["price"] == 4.25

    def test_add_inventory_unit_defaults_to_unit(self):
        token = _new_store_account("unit")
        name = _n("NoUnitItem")
        client.post(
            "/inventory/add-inventory",
            json={"name": name, "quantity": 5, "category": "OTHER"},
            headers=_headers(token),
        )
        inv = client.get("/inventory/get-store-inventory", headers=_headers(token)).json()["inventory"]
        item = next(i for i in inv if i["name"] == name)
        assert item["unit"] == "UNIT"

    def test_add_inventory_with_explicit_kg_unit(self):
        token = _new_store_account("unit")
        name = _n("KgItem")
        r = client.post(
            "/inventory/add-inventory",
            json={"name": name, "quantity": 10, "unit": "KG", "category": "PRODUCE", "price": 2.5},
            headers=_headers(token),
        )
        assert r.status_code == 200
        inv = client.get("/inventory/get-store-inventory", headers=_headers(token)).json()["inventory"]
        item = next(i for i in inv if i["name"] == name)
        assert item["unit"] == "KG"
        assert item["quantity"] == 10

    def test_add_inventory_reorder_keeps_original_unit(self):
        """Re-ordering an existing item shouldn't silently change its unit,
        even if a different unit is passed the second time."""
        token = _new_store_account("unit")
        name = _n("GramItem")
        client.post(
            "/inventory/add-inventory",
            json={"name": name, "quantity": 500, "unit": "G", "category": "DAIRY", "price": 3.0},
            headers=_headers(token),
        )
        r = client.post(
            "/inventory/add-inventory",
            json={"name": name, "quantity": 1, "unit": "KG", "category": "DAIRY", "price": 3.0},
            headers=_headers(token),
        )
        assert r.status_code == 200
        inv = client.get("/inventory/get-store-inventory", headers=_headers(token)).json()["inventory"]
        item = next(i for i in inv if i["name"] == name)
        assert item["unit"] == "G"  # unchanged from the original add
        assert item["quantity"] == 501

    def test_update_inventory_unit(self):
        token = _new_store_account("unit")
        item_id = _add_item(token, _n("FixUnitItem"), quantity=5, category="OTHER")
        r = client.put(
            f"/inventory/{item_id}",
            json={"unit": "KG"},
            headers=_headers(token),
        )
        assert r.status_code == 200
        inv = client.get("/inventory/get-store-inventory", headers=_headers(token)).json()["inventory"]
        item = next(i for i in inv if i["id"] == item_id)
        assert item["unit"] == "KG"
        assert item["quantity"] == 5  # unit-only update leaves quantity unchanged


# ─────────────────────────────────────────────────────────────────────────────
# INVENTORY: get-store-inventory — items filter, expiry + promo enrichment
# ─────────────────────────────────────────────────────────────────────────────

class TestGetStoreInventory:

    def test_get_store_inventory_items_filter(self):
        token = _new_store_account("filter")
        name_a = _n("FilterA")
        name_b = _n("FilterB")
        client.post("/inventory/add-inventory", json={"name": name_a, "quantity": 5, "category": "OTHER"}, headers=_headers(token))
        client.post("/inventory/add-inventory", json={"name": name_b, "quantity": 5, "category": "OTHER"}, headers=_headers(token))

        r = client.get("/inventory/get-store-inventory", params={"items": name_a}, headers=_headers(token))
        assert r.status_code == 200
        names = [i["name"] for i in r.json()["inventory"]]
        assert names == [name_a]

    def test_get_store_inventory_includes_expiry_and_sale_price(self):
        token = _new_store_account("enrich")
        inv_id = _add_item(token, _n("ExpiringGood"), 5, price=4.0)

        expiry = (date.today() + timedelta(days=3)).isoformat()
        r = client.put(f"/inventory/{inv_id}/expiry", json={"expiry_date": expiry}, headers=_headers(token))
        assert r.status_code == 200

        r = client.post(
            f"/inventory/{inv_id}/promotion",
            json={
                "sale_price": 2.5,
                "start_date": date.today().isoformat(),
                "end_date": (date.today() + timedelta(days=5)).isoformat(),
            },
            headers=_headers(token),
        )
        assert r.status_code == 200

        r = client.get("/inventory/get-store-inventory", headers=_headers(token))
        assert r.status_code == 200
        item = next(i for i in r.json()["inventory"] if i["id"] == inv_id)
        assert item["expiry_date"] == expiry
        assert item["sale_price"] == 2.5


# ─────────────────────────────────────────────────────────────────────────────
# INVENTORY: threshold endpoint
# ─────────────────────────────────────────────────────────────────────────────

class TestThresholdEndpoint:

    def test_set_threshold_requires_store(self):
        token = _new_user_account("nostore")
        r = client.put(f"/inventory/{uuid.uuid4()}/threshold", json={"threshold": 5}, headers=_headers(token))
        assert r.status_code == 403

    def test_set_threshold_item_not_found(self):
        token = _new_store_account("thresh")
        r = client.put(f"/inventory/{uuid.uuid4()}/threshold", json={"threshold": 5}, headers=_headers(token))
        assert r.status_code == 404
        assert r.json()["detail"] == "Inventory item not found"

    def test_set_threshold_create_then_update(self):
        token = _new_store_account("thresh")
        inv_id = _add_item(token, _n("Milk"), 30, category="DAIRY")

        r1 = client.put(f"/inventory/{inv_id}/threshold", json={"threshold": 10}, headers=_headers(token))
        assert r1.status_code == 200
        assert r1.json()["status"] == "success"

        r2 = client.put(f"/inventory/{inv_id}/threshold", json={"threshold": 15}, headers=_headers(token))
        assert r2.status_code == 200
        assert r2.json()["status"] == "success"

    def test_set_threshold_requires_auth(self):
        r = client.put(f"/inventory/{uuid.uuid4()}/threshold", json={"threshold": 5})
        assert r.status_code == 401


# ─────────────────────────────────────────────────────────────────────────────
# INVENTORY: expiry endpoint
# ─────────────────────────────────────────────────────────────────────────────

class TestExpiryEndpoint:

    def test_set_expiry_requires_store(self):
        token = _new_user_account("nostore")
        r = client.put(
            f"/inventory/{uuid.uuid4()}/expiry",
            json={"expiry_date": date.today().isoformat()},
            headers=_headers(token),
        )
        assert r.status_code == 403

    def test_set_expiry_item_not_found(self):
        token = _new_store_account("expiry")
        r = client.put(
            f"/inventory/{uuid.uuid4()}/expiry",
            json={"expiry_date": date.today().isoformat()},
            headers=_headers(token),
        )
        assert r.status_code == 404

    def test_set_expiry_create_then_update(self):
        token = _new_store_account("expiry")
        inv_id = _add_item(token, _n("Yogurt"), 10, category="DAIRY")

        d1 = (date.today() + timedelta(days=2)).isoformat()
        r1 = client.put(f"/inventory/{inv_id}/expiry", json={"expiry_date": d1}, headers=_headers(token))
        assert r1.status_code == 200

        d2 = (date.today() + timedelta(days=9)).isoformat()
        r2 = client.put(f"/inventory/{inv_id}/expiry", json={"expiry_date": d2}, headers=_headers(token))
        assert r2.status_code == 200


# ─────────────────────────────────────────────────────────────────────────────
# INVENTORY: promotion set / delete
# ─────────────────────────────────────────────────────────────────────────────

class TestPromotionEndpoint:

    def test_set_promotion_requires_store(self):
        token = _new_user_account("nostore")
        r = client.post(
            f"/inventory/{uuid.uuid4()}/promotion",
            json={"sale_price": 1.99, "start_date": date.today().isoformat(), "end_date": (date.today() + timedelta(days=3)).isoformat()},
            headers=_headers(token),
        )
        assert r.status_code == 403

    def test_set_promotion_item_not_found(self):
        token = _new_store_account("promo")
        r = client.post(
            f"/inventory/{uuid.uuid4()}/promotion",
            json={"sale_price": 1.99, "start_date": date.today().isoformat(), "end_date": (date.today() + timedelta(days=3)).isoformat()},
            headers=_headers(token),
        )
        assert r.status_code == 404

    def test_set_promotion_invalid_date_range(self):
        token = _new_store_account("promo")
        inv_id = _add_item(token, _n("PromoBad"), 5, price=5.0)
        r = client.post(
            f"/inventory/{inv_id}/promotion",
            json={
                "sale_price": 3.0,
                "start_date": date.today().isoformat(),
                "end_date": (date.today() - timedelta(days=1)).isoformat(),
            },
            headers=_headers(token),
        )
        assert r.status_code == 400
        assert "end_date must be on or after start_date" in r.json()["detail"]

    def test_set_promotion_sale_price_must_be_positive(self):
        token = _new_store_account("promo")
        inv_id = _add_item(token, _n("InvalidPromoPrice"), 5, price=5.0)
        r = client.post(
            f"/inventory/{inv_id}/promotion",
            json={"sale_price": 0, "start_date": date.today().isoformat(), "end_date": (date.today() + timedelta(days=5)).isoformat()},
            headers=_headers(token),
        )
        assert r.status_code == 422

    def test_set_promotion_create_then_update(self):
        token = _new_store_account("promo")
        inv_id = _add_item(token, _n("PromoGood"), 5, price=10.0)

        r1 = client.post(
            f"/inventory/{inv_id}/promotion",
            json={"sale_price": 7.0, "start_date": date.today().isoformat(), "end_date": (date.today() + timedelta(days=5)).isoformat()},
            headers=_headers(token),
        )
        assert r1.status_code == 200
        assert r1.json()["status"] == "success"

        r2 = client.post(
            f"/inventory/{inv_id}/promotion",
            json={"sale_price": 6.5, "start_date": date.today().isoformat(), "end_date": (date.today() + timedelta(days=10)).isoformat()},
            headers=_headers(token),
        )
        assert r2.status_code == 200

        inv = client.get("/inventory/get-store-inventory", headers=_headers(token)).json()["inventory"]
        item = next(i for i in inv if i["id"] == inv_id)
        assert item["sale_price"] == 6.5


class TestDeletePromotion:

    def test_delete_promotion_requires_store(self):
        token = _new_user_account("nostore")
        r = client.delete(f"/inventory/{uuid.uuid4()}/promotion", headers=_headers(token))
        assert r.status_code == 403

    def test_delete_promotion_item_not_found(self):
        token = _new_store_account("delpromo")
        r = client.delete(f"/inventory/{uuid.uuid4()}/promotion", headers=_headers(token))
        assert r.status_code == 404

    def test_delete_promotion_when_none_exists_is_noop_success(self):
        token = _new_store_account("delpromo")
        inv_id = _add_item(token, _n("NoPromoItem"), 5)
        r = client.delete(f"/inventory/{inv_id}/promotion", headers=_headers(token))
        assert r.status_code == 200
        assert r.json()["status"] == "success"

    def test_delete_promotion_removes_existing(self):
        token = _new_store_account("delpromo")
        inv_id = _add_item(token, _n("HasPromoItem"), 5, price=5.0)
        client.post(
            f"/inventory/{inv_id}/promotion",
            json={"sale_price": 3.0, "start_date": date.today().isoformat(), "end_date": (date.today() + timedelta(days=5)).isoformat()},
            headers=_headers(token),
        )
        r = client.delete(f"/inventory/{inv_id}/promotion", headers=_headers(token))
        assert r.status_code == 200

        inv = client.get("/inventory/get-store-inventory", headers=_headers(token)).json()["inventory"]
        item = next(i for i in inv if i["id"] == inv_id)
        assert item["sale_price"] is None


# ─────────────────────────────────────────────────────────────────────────────
# INVENTORY: PUT /{inventory_id} (quantity/price update) + threshold/back-in-
# stock trigger branches inside InventoryHelper.update_inventory_fields
# ─────────────────────────────────────────────────────────────────────────────

class TestUpdateInventoryEndpoint:

    def test_update_inventory_success_quantity_and_price(self):
        token = _new_store_account("update")
        inv_id = _add_item(token, _n("UpdateMe"), 10, price=1.0)
        r = client.put(f"/inventory/{inv_id}", json={"quantity": 25, "price": 2.5}, headers=_headers(token))
        assert r.status_code == 200
        assert r.json()["status"] == "success"

        inv = client.get("/inventory/get-store-inventory", headers=_headers(token)).json()["inventory"]
        item = next(i for i in inv if i["id"] == inv_id)
        assert item["quantity"] == 25
        assert item["price"] == 2.5

    def test_update_inventory_not_found(self):
        token = _new_store_account("update")
        r = client.put(f"/inventory/{uuid.uuid4()}", json={"quantity": 1}, headers=_headers(token))
        assert r.status_code == 404

    def test_update_inventory_requires_auth(self):
        r = client.put(f"/inventory/{uuid.uuid4()}", json={"quantity": 1})
        assert r.status_code == 401

    def test_update_inventory_triggers_low_stock_alert(self):
        """Quantity dropping to/below an explicit threshold flips
        StockThreshold.is_triggered (inventory_helper.py lines 141-145)."""
        token = _new_store_account("lowstock")
        inv_id = _add_item(token, _n("LowStockTrigger"), 50)
        client.put(f"/inventory/{inv_id}/threshold", json={"threshold": 10}, headers=_headers(token))

        r = client.put(f"/inventory/{inv_id}", json={"quantity": 5}, headers=_headers(token))
        assert r.status_code == 200

    def test_update_inventory_triggers_back_in_stock(self):
        """quantity 0 -> positive fires trigger_back_in_stock()
        (inventory_helper.py lines 152-153)."""
        token = _new_store_account("backinstock")
        inv_id = _add_item(token, _n("BackInStockTrigger"), 5)

        r1 = client.put(f"/inventory/{inv_id}", json={"quantity": 0}, headers=_headers(token))
        assert r1.status_code == 200
        r2 = client.put(f"/inventory/{inv_id}", json={"quantity": 8}, headers=_headers(token))
        assert r2.status_code == 200


# ─────────────────────────────────────────────────────────────────────────────
# INVENTORY: /search
# ─────────────────────────────────────────────────────────────────────────────

class TestSearchInventory:

    def test_search_query_too_short(self):
        r = client.get("/inventory/search", params={"q": "a"})
        assert r.status_code == 422

    def test_search_no_matches_returns_empty(self):
        q = f"zzzznomatch{_suffix}"
        r = client.get("/inventory/search", params={"q": q})
        assert r.status_code == 200
        assert r.json() == {"query": q, "results": []}

    def test_search_finds_item_with_price_filters(self):
        token = _new_store_account("search")
        name = _n("SearchableWidget")
        _add_item(token, name, 5, price=3.5)

        r = client.get("/inventory/search", params={"q": name[:15]})
        assert r.status_code == 200
        results = r.json()["results"]
        match = next(i for i in results if i["name"] == name)
        assert match["price"] == 3.5
        assert match["store_name"]
        assert match["sale_price"] is None

        r2 = client.get("/inventory/search", params={"q": name[:15], "min_price": 4.0})
        assert all(i["name"] != name for i in r2.json()["results"])

        r3 = client.get("/inventory/search", params={"q": name[:15], "min_price": 3.5, "max_price": 3.5})
        assert any(i["name"] == name for i in r3.json()["results"])

    def test_search_filters_by_category(self):
        token = _new_store_account("search")
        name = _n("CatSearchItem")
        _add_item(token, name, 5, category="BAKERY", price=2.0)

        r = client.get("/inventory/search", params={"q": name[:12], "category": "BAKERY"})
        assert any(i["name"] == name for i in r.json()["results"])

        r2 = client.get("/inventory/search", params={"q": name[:12], "category": "MEAT"})
        assert all(i["name"] != name for i in r2.json()["results"])

    def test_search_in_stock_false_includes_zero_stock(self):
        token = _new_store_account("search")
        name = _n("ZeroStockItem")
        _add_item(token, name, 0)

        r = client.get("/inventory/search", params={"q": name[:12]})
        assert all(i["name"] != name for i in r.json()["results"])

        r2 = client.get("/inventory/search", params={"q": name[:12], "in_stock": False})
        assert any(i["name"] == name for i in r2.json()["results"])

    def test_search_by_store_id_filters(self):
        token = _new_store_account("search")
        name = _n("StoreScopedItem")
        _add_item(token, name, 5)
        stores = client.get("/stores/my-stores", headers=_headers(token)).json()
        store_id = stores[0]["id"]

        r = client.get("/inventory/search", params={"q": name[:12], "store_id": store_id})
        assert any(i["name"] == name for i in r.json()["results"])

        r2 = client.get("/inventory/search", params={"q": name[:12], "store_id": str(uuid.uuid4())})
        assert r2.json()["results"] == []

    def test_search_excludes_inactive_store(self):
        token = _new_store_account("search")
        name = _n("InactiveStoreItem")
        _add_item(token, name, 5)
        stores = client.get("/stores/my-stores", headers=_headers(token)).json()
        store_id = stores[0]["id"]
        deact = client.post(f"/stores/{store_id}/deactivate", headers=_headers(token))
        assert deact.status_code == 200

        r = client.get("/inventory/search", params={"q": name[:12]})
        assert r.status_code == 200
        assert r.json()["results"] == []

    def test_search_with_active_promotion_shows_sale_price(self):
        token = _new_store_account("search")
        name = _n("OnSaleItem")
        inv_id = _add_item(token, name, 5, price=10.0)
        client.post(
            f"/inventory/{inv_id}/promotion",
            json={"sale_price": 7.5, "start_date": date.today().isoformat(), "end_date": (date.today() + timedelta(days=5)).isoformat()},
            headers=_headers(token),
        )
        r = client.get("/inventory/search", params={"q": name[:12]})
        assert r.status_code == 200
        match = next(i for i in r.json()["results"] if i["name"] == name)
        assert match["sale_price"] == 7.5


# ─────────────────────────────────────────────────────────────────────────────
# INVENTORY: /browse/{store_id}
# ─────────────────────────────────────────────────────────────────────────────

class TestBrowseStoreInventory:

    def test_browse_requires_auth(self):
        r = client.get(f"/inventory/browse/{uuid.uuid4()}")
        assert r.status_code == 401

    def test_browse_empty_store_returns_empty_list(self):
        token = _new_user_account("browser")
        r = client.get(f"/inventory/browse/{uuid.uuid4()}", headers=_headers(token))
        assert r.status_code == 200
        assert r.json()["inventory"] == []

    def test_browse_returns_items_with_promo_and_flash_fields(self):
        store_token = _new_store_account("browse")
        name = _n("BrowseItem")
        _add_item(store_token, name, 8, category="GROCERY", price=2.0)
        stores = client.get("/stores/my-stores", headers=_headers(store_token)).json()
        store_id = stores[0]["id"]

        user_token = _new_user_account("browser")
        r = client.get(f"/inventory/browse/{store_id}", headers=_headers(user_token))
        assert r.status_code == 200
        items = r.json()["inventory"]
        item = next(i for i in items if i["name"] == name)
        assert item["sale_price"] is None
        assert item["flash_sale_price"] is None
        assert item["flash_sale_end_at"] is None


# ─────────────────────────────────────────────────────────────────────────────
# INVENTORY: /trending
# ─────────────────────────────────────────────────────────────────────────────

class TestTrending:

    def test_trending_returns_ok_list(self):
        r = client.get("/inventory/trending")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_trending_includes_recent_order_item(self):
        store_token = _new_store_account("trend")
        name = _n("TrendItem")
        inv_id = _add_item(store_token, name, 50, category="GROCERY", price=5.0)
        user_token = _new_user_account("trend")

        for _ in range(2):
            with patch("engine.mailer.Mailer.send"):
                r = client.post(
                    "/order/create-order",
                    json={"items": [{"inventory_id": inv_id, "quantity": 3}]},
                    headers=_headers(user_token),
                )
            assert r.status_code == 200, r.text

        r2 = client.get("/inventory/trending", params={"limit": 50})
        assert r2.status_code == 200
        items = r2.json()
        match = next((i for i in items if i["inventory_id"] == inv_id), None)
        assert match is not None
        assert match["order_count"] >= 2
        assert match["inventory_name"] == name
        assert match["store_name"]
        assert match["is_verified_store"] is False

    def test_trending_respects_limit(self):
        store_token = _new_store_account("trendlimit")
        user_token = _new_user_account("trendlimit")
        for i in range(2):
            inv_id = _add_item(store_token, _n(f"LimitItem{i}"), 50, price=1.0)
            with patch("engine.mailer.Mailer.send"):
                r = client.post(
                    "/order/create-order",
                    json={"items": [{"inventory_id": inv_id, "quantity": 1}]},
                    headers=_headers(user_token),
                )
            assert r.status_code == 200, r.text

        r = client.get("/inventory/trending", params={"limit": 1})
        assert r.status_code == 200
        assert len(r.json()) <= 1

    def test_trending_limit_over_max_rejected(self):
        r = client.get("/inventory/trending", params={"limit": 51})
        assert r.status_code == 422


# ─────────────────────────────────────────────────────────────────────────────
# DASHBOARD (api/dashboard_api.py)
# ─────────────────────────────────────────────────────────────────────────────

class TestDashboard:

    def test_dashboard_requires_store(self):
        token = _new_user_account("nostore")
        r = client.get("/dashboard/", headers=_headers(token))
        assert r.status_code == 403

    def test_dashboard_requires_auth(self):
        r = client.get("/dashboard/")
        assert r.status_code == 401

    def test_dashboard_low_stock_branches(self):
        token = _new_store_account("lowstockdash")

        low_default = _add_item(token, _n("LowDefault"), 5)          # no threshold, qty < 20 -> low
        not_low_default = _add_item(token, _n("NotLowDefault"), 25)  # no threshold, qty >= 20 -> not low
        low_explicit = _add_item(token, _n("LowExplicit"), 10)       # threshold=10, qty<=10 -> low
        not_low_explicit = _add_item(token, _n("NotLowExplicit"), 11)  # threshold=10, qty>10 -> not low

        client.put(f"/inventory/{low_explicit}/threshold", json={"threshold": 10}, headers=_headers(token))
        client.put(f"/inventory/{not_low_explicit}/threshold", json={"threshold": 10}, headers=_headers(token))

        r = client.get("/dashboard/", headers=_headers(token))
        assert r.status_code == 200
        low_stock = r.json()["low_stock"]
        low_ids = {i["id"] for i in low_stock}

        assert low_default in low_ids
        assert not_low_default not in low_ids
        assert low_explicit in low_ids
        assert not_low_explicit not in low_ids

        default_entry = next(i for i in low_stock if i["id"] == low_default)
        assert default_entry["threshold"] == 20
        explicit_entry = next(i for i in low_stock if i["id"] == low_explicit)
        assert explicit_entry["threshold"] == 10

    def test_dashboard_expiring_soon_dedup_and_window(self):
        token = _new_store_account("expiringdash")
        inv_id = _add_item(token, _n("YogurtExpiring"), 10, category="DAIRY")

        later = (date.today() + timedelta(days=5)).isoformat()
        r = client.put(f"/inventory/{inv_id}/expiry", json={"expiry_date": later}, headers=_headers(token))
        assert r.status_code == 200

        # Insert a second, earlier expiry row directly so we can verify the
        # dashboard dedups per-item and keeps the *earliest* expiry.
        from models.db import db_session
        from models.entity.inventory_expiry_entity import InventoryExpiry
        # dashboard_api.py computes "today" as datetime.utcnow().date(), not
        # local date.today() — match that reference frame so this assertion
        # doesn't flake depending on the local/UTC day boundary.
        earliest_date = datetime.utcnow().date() + timedelta(days=2)
        db_session.add(InventoryExpiry(inventory_id=uuid.UUID(inv_id), expiry_date=earliest_date))
        db_session.commit()

        r2 = client.get("/dashboard/", headers=_headers(token))
        assert r2.status_code == 200
        expiring = r2.json()["expiring_soon"]
        match = next(i for i in expiring if i["id"] == inv_id)
        assert match["days_remaining"] == 2
        # Only one entry for this item despite two InventoryExpiry rows.
        assert len([i for i in expiring if i["id"] == inv_id]) == 1

        # Item expiring outside the 7-day window must not appear.
        inv_id2 = _add_item(token, _n("FarExpiry"), 5, category="DAIRY")
        far = (date.today() + timedelta(days=20)).isoformat()
        client.put(f"/inventory/{inv_id2}/expiry", json={"expiry_date": far}, headers=_headers(token))

        r3 = client.get("/dashboard/", headers=_headers(token))
        ids_in_expiring = [i["id"] for i in r3.json()["expiring_soon"]]
        assert inv_id2 not in ids_in_expiring

    def test_dashboard_top_sellers_caps_at_five(self):
        store_token = _new_store_account("topsellers")
        user_token = _new_user_account("topsellers")

        quantities = [6, 5, 4, 3, 2, 1]
        inv_ids = [
            _add_item(store_token, _n(f"TopSeller{i}"), 100, category="GROCERY", price=1.0)
            for i in range(len(quantities))
        ]

        items_payload = [{"inventory_id": iid, "quantity": q} for iid, q in zip(inv_ids, quantities)]
        with patch("engine.mailer.Mailer.send"):
            r = client.post(
                "/order/create-order",
                json={"items": items_payload},
                headers=_headers(user_token),
            )
        assert r.status_code == 200, r.text

        r2 = client.get("/dashboard/", headers=_headers(store_token))
        assert r2.status_code == 200
        top_sellers = r2.json()["top_sellers"]
        assert len(top_sellers) == 5
        assert top_sellers[0]["units_sold"] == 6
        assert top_sellers[-1]["units_sold"] == 2
        # The 6th item (units_sold=1) must have been dropped by the top_n cap.
        assert all(t["units_sold"] != 1 for t in top_sellers)

    def test_dashboard_todays_orders_summary(self):
        store_token = _new_store_account("todaysummary")
        user_token = _new_user_account("todaysummary")
        inv_id = _add_item(store_token, _n("TodayGood"), 20, price=10.0)

        with patch("engine.mailer.Mailer.send"):
            r = client.post(
                "/order/create-order",
                json={"items": [{"inventory_id": inv_id, "quantity": 2}]},
                headers=_headers(user_token),
            )
        assert r.status_code == 200, r.text
        total_price = r.json()["total_price"]
        order_id = r.json()["id"]

        r2 = client.get("/dashboard/", headers=_headers(store_token))
        assert r2.status_code == 200
        summary = r2.json()["todays_summary"]
        assert summary["order_count"] == 1
        assert summary["revenue"] == total_price
        assert summary["orders"][0]["id"] == order_id
        assert summary["orders"][0]["status"] == "pending"


class TestRevenueTrend:

    def test_revenue_trend_requires_store(self):
        token = _new_user_account("nostore")
        r = client.get("/dashboard/revenue-trend", headers=_headers(token))
        assert r.status_code == 403

    def test_revenue_trend_requires_auth(self):
        r = client.get("/dashboard/revenue-trend")
        assert r.status_code == 401

    def test_revenue_trend_default_days(self):
        token = _new_store_account("trenddefault")
        r = client.get("/dashboard/revenue-trend", headers=_headers(token))
        assert r.status_code == 200
        assert len(r.json()["trend"]) == 30

    def test_revenue_trend_days_clamped_high(self):
        token = _new_store_account("trendhigh")
        r = client.get("/dashboard/revenue-trend", params={"days": 999}, headers=_headers(token))
        assert r.status_code == 200
        assert len(r.json()["trend"]) == 365

    def test_revenue_trend_days_clamped_low(self):
        token = _new_store_account("trendlow")
        r = client.get("/dashboard/revenue-trend", params={"days": 0}, headers=_headers(token))
        assert r.status_code == 200
        assert len(r.json()["trend"]) == 1

    def test_revenue_trend_reflects_order(self):
        store_token = _new_store_account("trendorder")
        user_token = _new_user_account("trendorder")
        inv_id = _add_item(store_token, _n("TrendGood"), 20, price=10.0)

        with patch("engine.mailer.Mailer.send"):
            r = client.post(
                "/order/create-order",
                json={"items": [{"inventory_id": inv_id, "quantity": 2}]},
                headers=_headers(user_token),
            )
        assert r.status_code == 200, r.text
        total_price = r.json()["total_price"]

        r2 = client.get("/dashboard/revenue-trend", params={"days": 7}, headers=_headers(store_token))
        assert r2.status_code == 200
        trend = r2.json()["trend"]
        # dashboard_api.py buckets by datetime.utcnow().date(), not local
        # date.today() — match that reference frame here too.
        today_str = datetime.utcnow().date().isoformat()
        today_point = next(p for p in trend if p["date"] == today_str)
        assert today_point["order_count"] == 1
        assert today_point["revenue"] == total_price
