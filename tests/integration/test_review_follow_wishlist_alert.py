"""
Integration tests for product reviews, store follows, wishlist, price alerts,
and stock alerts.

Covers:
  - api/product_review_api.py
  - api/store_follow_api.py
  - api/wishlist_api.py
  - api/price_alert_api.py
  - api/stock_alert_api.py

Reuses the module-scoped fixtures from tests/integration/conftest.py
(user_token, user_profile, store_token, store_id, store_profile,
inventory_id, other_store_token) for the common case, and defines a small
set of additional module-scoped fixtures below for scenarios those don't
cover: a second profiled user (ownership / "not mine" checks), a store
account with no Store row at all ("profile not set" checks), and a second
profiled store (stock-alert cross-store ownership checks).
"""

import uuid
from datetime import date, timedelta

import pytest

from tests.integration.helpers import (_headers, _login, _otp_and_verify,
                                       _register, client)

# ─────────────────────────────────────────────────────────────────────────────
# Unique phone numbers for this file only (own suffix -> no collisions with
# helpers.py's shared USER_PHONE/STORE_PHONE/OTHER_PHONE or other test files).
# ─────────────────────────────────────────────────────────────────────────────
_suffix = str(uuid.uuid4().int)[:6]
USER2_PHONE = f"+1567{_suffix}01"
NOPROFILE_STORE_PHONE = f"+1567{_suffix}02"
STORE2_PHONE = f"+1567{_suffix}03"


@pytest.fixture(scope="module")
def user2_token():
    """A second regular user, profile set — used for ownership / 'not mine' checks."""
    _otp_and_verify(USER2_PHONE)
    _register(USER2_PHONE, "user")
    token = _login(USER2_PHONE)
    r = client.post(
        "/user/set-profile",
        json={
            "name": "Second User",
            "email": "user2@groceror.test",
            "location": "User2 City",
        },
        headers=_headers(token),
    )
    assert r.status_code == 200, r.text
    return token


@pytest.fixture(scope="module")
def noprofile_store_token():
    """A store-type account that never sets a Store profile (no Store row at all)."""
    _otp_and_verify(NOPROFILE_STORE_PHONE)
    _register(NOPROFILE_STORE_PHONE, "store")
    return _login(NOPROFILE_STORE_PHONE)


@pytest.fixture(scope="module")
def store2_token():
    """A second store account (used to prove it does NOT own the first store's inventory)."""
    _otp_and_verify(STORE2_PHONE)
    _register(STORE2_PHONE, "store")
    return _login(STORE2_PHONE)


@pytest.fixture(scope="module")
def store2_id(store2_token):
    r = client.post(
        "/stores/",
        json={"name": "Rival Market", "email": "rival@groceror.test"},
        headers=_headers(store2_token),
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


# ─────────────────────────────────────────────────────────────────────────────
# PRODUCT REVIEWS
# ─────────────────────────────────────────────────────────────────────────────


class TestProductReviews:

    def test_submit_review_requires_profile(self, store_token, inventory_id):
        """store_token's entity has no User row -> _get_user returns 400."""
        r = client.post(
            "/product-reviews",
            json={"inventory_id": inventory_id, "rating": 5},
            headers=_headers(store_token),
        )
        assert r.status_code == 400
        assert r.json()["detail"] == "User profile not set"

    def test_submit_review_item_not_found(self, user_token, user_profile):
        fake_id = str(uuid.uuid4())
        r = client.post(
            "/product-reviews",
            json={"inventory_id": fake_id, "rating": 5},
            headers=_headers(user_token),
        )
        assert r.status_code == 404
        assert r.json()["detail"] == "Item not found"

    def test_submit_review_invalid_rating_too_high(
        self, user_token, user_profile, inventory_id
    ):
        r = client.post(
            "/product-reviews",
            json={"inventory_id": inventory_id, "rating": 6},
            headers=_headers(user_token),
        )
        assert r.status_code == 422

    def test_submit_review_invalid_rating_too_low(
        self, user_token, user_profile, inventory_id
    ):
        r = client.post(
            "/product-reviews",
            json={"inventory_id": inventory_id, "rating": 0},
            headers=_headers(user_token),
        )
        assert r.status_code == 422

    def test_submit_review_creates(self, user_token, user_profile, inventory_id):
        r = client.post(
            "/product-reviews",
            json={"inventory_id": inventory_id, "rating": 4, "comment": "Pretty good"},
            headers=_headers(user_token),
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["inventory_id"] == inventory_id
        assert data["rating"] == 4
        assert data["comment"] == "Pretty good"
        uuid.UUID(data["id"])
        uuid.UUID(data["user_id"])

    def test_submit_review_updates_existing(
        self, user_token, user_profile, inventory_id
    ):
        """Submitting again for the same item updates in place, no duplicate row."""
        first = client.post(
            "/product-reviews",
            json={"inventory_id": inventory_id, "rating": 4, "comment": "Pretty good"},
            headers=_headers(user_token),
        ).json()

        r = client.post(
            "/product-reviews",
            json={
                "inventory_id": inventory_id,
                "rating": 2,
                "comment": "Changed my mind",
            },
            headers=_headers(user_token),
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["id"] == first["id"]
        assert data["rating"] == 2
        assert data["comment"] == "Changed my mind"

    def test_get_reviews_summary(self, user_token, user_profile, inventory_id):
        r = client.get(f"/product-reviews/{inventory_id}", headers=_headers(user_token))
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["review_count"] == 1
        assert data["avg_rating"] == 2
        assert len(data["reviews"]) == 1
        assert data["my_review"] is not None
        assert data["my_review"]["rating"] == 2

    def test_get_reviews_my_review_none_without_user_row(
        self, store_token, user_token, user_profile, inventory_id
    ):
        """Authenticated as an entity with no User row -> my_review stays None,
        but the review list itself is still populated."""
        r = client.get(
            f"/product-reviews/{inventory_id}", headers=_headers(store_token)
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["review_count"] == 1
        assert data["my_review"] is None

    def test_get_reviews_no_reviews(self, user_token):
        fake_id = str(uuid.uuid4())
        r = client.get(f"/product-reviews/{fake_id}", headers=_headers(user_token))
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["avg_rating"] is None
        assert data["review_count"] == 0
        assert data["reviews"] == []
        assert data["my_review"] is None

    def test_delete_review_not_found(self, user_token, user_profile):
        fake_id = str(uuid.uuid4())
        r = client.delete(f"/product-reviews/{fake_id}", headers=_headers(user_token))
        assert r.status_code == 404
        assert r.json()["detail"] == "Review not found"

    def test_delete_review_wrong_owner(
        self, user_token, user_profile, user2_token, inventory_id
    ):
        """A review id that exists, but doesn't belong to the caller -> 404 (not 403)."""
        mine = client.get(
            f"/product-reviews/{inventory_id}", headers=_headers(user_token)
        ).json()
        review_id = mine["my_review"]["id"]

        r = client.delete(
            f"/product-reviews/{review_id}", headers=_headers(user2_token)
        )
        assert r.status_code == 404
        assert r.json()["detail"] == "Review not found"

    def test_delete_review_success(self, user_token, user_profile, inventory_id):
        mine = client.get(
            f"/product-reviews/{inventory_id}", headers=_headers(user_token)
        ).json()
        review_id = mine["my_review"]["id"]

        r = client.delete(f"/product-reviews/{review_id}", headers=_headers(user_token))
        assert r.status_code == 204

        after = client.get(
            f"/product-reviews/{inventory_id}", headers=_headers(user_token)
        ).json()
        assert after["review_count"] == 0
        assert after["my_review"] is None


# ─────────────────────────────────────────────────────────────────────────────
# STORE FOLLOW
# ─────────────────────────────────────────────────────────────────────────────


class TestStoreFollow:

    def test_follow_requires_profile(self, store_token, store_id):
        r = client.post(f"/stores/{store_id}/follow", headers=_headers(store_token))
        assert r.status_code == 400
        assert r.json()["detail"] == "User profile not set"

    def test_follow_store_not_found(self, user_token, user_profile):
        fake_id = str(uuid.uuid4())
        r = client.post(f"/stores/{fake_id}/follow", headers=_headers(user_token))
        assert r.status_code == 404
        assert r.json()["detail"] == "Store not found"

    def test_follow_store_success(
        self, user_token, user_profile, store_id, store_profile
    ):
        r = client.post(f"/stores/{store_id}/follow", headers=_headers(user_token))
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["store_id"] == store_id
        assert data["store_name"] == "Fresh Market"
        assert data["is_active"] is True
        assert data["follower_count"] == 1
        assert "followed_at" in data

    def test_follow_store_idempotent(self, user_token, user_profile, store_id):
        r = client.post(f"/stores/{store_id}/follow", headers=_headers(user_token))
        assert r.status_code == 200, r.text
        assert r.json()["follower_count"] == 1

    def test_list_following(self, user_token, user_profile, store_id):
        r = client.get("/stores/following", headers=_headers(user_token))
        assert r.status_code == 200, r.text
        ids = [f["store_id"] for f in r.json()]
        assert store_id in ids

    def test_get_follower_count(self, user_token, user_profile, user2_token, store_id):
        r = client.get(f"/stores/{store_id}/followers", headers=_headers(user_token))
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["store_id"] == store_id
        assert data["follower_count"] == 1
        assert data["is_following"] is True

        r = client.get(f"/stores/{store_id}/followers", headers=_headers(user2_token))
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["follower_count"] == 1
        assert data["is_following"] is False

    def test_get_follower_count_store_not_found(self, user_token):
        fake_id = str(uuid.uuid4())
        r = client.get(f"/stores/{fake_id}/followers", headers=_headers(user_token))
        assert r.status_code == 404
        assert r.json()["detail"] == "Store not found"

    def test_unfollow_store_success(self, user_token, user_profile, store_id):
        r = client.delete(f"/stores/{store_id}/follow", headers=_headers(user_token))
        assert r.status_code == 204

        r = client.get("/stores/following", headers=_headers(user_token))
        ids = [f["store_id"] for f in r.json()]
        assert store_id not in ids

    def test_unfollow_store_noop_when_not_following(self, user2_token, store_id):
        """Deleting a follow that never existed is a no-op, still 204."""
        r = client.delete(f"/stores/{store_id}/follow", headers=_headers(user2_token))
        assert r.status_code == 204


# ─────────────────────────────────────────────────────────────────────────────
# WISHLIST
# ─────────────────────────────────────────────────────────────────────────────


class TestWishlist:

    def test_add_wishlist_requires_profile(self, store_token, inventory_id):
        r = client.post(
            "/wishlist",
            json={"inventory_id": inventory_id},
            headers=_headers(store_token),
        )
        assert r.status_code == 400
        assert r.json()["detail"] == "User profile not set"

    def test_add_wishlist_item_not_found(self, user_token, user_profile):
        fake_id = str(uuid.uuid4())
        r = client.post(
            "/wishlist",
            json={"inventory_id": fake_id},
            headers=_headers(user_token),
        )
        assert r.status_code == 404
        assert r.json()["detail"] == "Item not found"

    def test_add_wishlist_success(
        self, user_token, user_profile, inventory_id, store_id
    ):
        r = client.post(
            "/wishlist",
            json={"inventory_id": inventory_id},
            headers=_headers(user_token),
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["inventory_id"] == inventory_id
        assert data["inventory_name"] == "Apples"
        assert data["store_id"] == store_id
        assert data["store_name"] == "Fresh Market"
        assert data["sale_price"] is None
        # Not `== 50`: the shared conftest.py `inventory_id` fixture upserts
        # by (store, name) — add_inventory() increments quantity on an
        # existing "Apples" row rather than creating a fresh one, so the
        # exact stock figure here depends on how many other test files also
        # requested this fixture and is not deterministic across the suite.
        assert data["stock"] >= 50
        assert data["is_in_stock"] is True
        assert "added_at" in data

    def test_add_wishlist_idempotent(self, user_token, user_profile, inventory_id):
        r = client.post(
            "/wishlist",
            json={"inventory_id": inventory_id},
            headers=_headers(user_token),
        )
        assert r.status_code == 200, r.text
        assert r.json()["inventory_id"] == inventory_id

    def test_check_wishlist_true(self, user_token, user_profile, inventory_id):
        r = client.get(f"/wishlist/check/{inventory_id}", headers=_headers(user_token))
        assert r.status_code == 200
        assert r.json() is True

    def test_check_wishlist_false(self, user_token, user_profile):
        fake_id = str(uuid.uuid4())
        r = client.get(f"/wishlist/check/{fake_id}", headers=_headers(user_token))
        assert r.status_code == 200
        assert r.json() is False

    def test_list_wishlist(self, user_token, user_profile, inventory_id):
        r = client.get("/wishlist", headers=_headers(user_token))
        assert r.status_code == 200, r.text
        ids = [i["inventory_id"] for i in r.json()]
        assert inventory_id in ids

    def test_wishlist_reflects_active_promotion(
        self, user_token, user_profile, store_token, store_profile, inventory_id
    ):
        promo_payload = {
            "sale_price": 1.50,
            "start_date": date.today().isoformat(),
            "end_date": (date.today() + timedelta(days=7)).isoformat(),
        }
        r = client.post(
            f"/inventory/{inventory_id}/promotion",
            json=promo_payload,
            headers=_headers(store_token),
        )
        assert r.status_code == 200, r.text

        r = client.get("/wishlist", headers=_headers(user_token))
        assert r.status_code == 200, r.text
        item = next(i for i in r.json() if i["inventory_id"] == inventory_id)
        assert item["sale_price"] == 1.50

    def test_remove_from_wishlist_success(self, user_token, user_profile, inventory_id):
        r = client.delete(f"/wishlist/{inventory_id}", headers=_headers(user_token))
        assert r.status_code == 204

        r = client.get(f"/wishlist/check/{inventory_id}", headers=_headers(user_token))
        assert r.json() is False

    def test_remove_from_wishlist_noop(self, user_token, user_profile):
        fake_id = str(uuid.uuid4())
        r = client.delete(f"/wishlist/{fake_id}", headers=_headers(user_token))
        assert r.status_code == 204


# ─────────────────────────────────────────────────────────────────────────────
# PRICE ALERTS
# ─────────────────────────────────────────────────────────────────────────────


class TestPriceAlerts:

    def test_create_price_alert_requires_profile(self, store_token, inventory_id):
        r = client.post(
            "/price-alerts",
            json={"inventory_id": inventory_id, "target_price": 5.0},
            headers=_headers(store_token),
        )
        assert r.status_code == 400
        assert r.json()["detail"] == "User profile not set"

    def test_create_price_alert_item_not_found(self, user_token, user_profile):
        fake_id = str(uuid.uuid4())
        r = client.post(
            "/price-alerts",
            json={"inventory_id": fake_id, "target_price": 5.0},
            headers=_headers(user_token),
        )
        assert r.status_code == 404
        assert r.json()["detail"] == "Inventory item not found"

    def test_create_price_alert_not_yet_triggered(
        self,
        user_token,
        user_profile,
        store_token,
        store_profile,
        store_id,
        inventory_id,
    ):
        # Give the item a known, nonzero price first.
        r = client.put(
            f"/inventory/{inventory_id}",
            json={"price": 10.0},
            headers=_headers(store_token),
        )
        assert r.status_code == 200, r.text

        r = client.post(
            "/price-alerts",
            json={"inventory_id": inventory_id, "target_price": 5.0},
            headers=_headers(user_token),
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["inventory_id"] == inventory_id
        assert data["current_price"] == 10.0
        assert data["target_price"] == 5.0
        assert data["is_triggered"] is False
        assert data["is_active"] is True
        assert data["store_id"] == store_id
        assert data["store_name"] == "Fresh Market"

    def test_create_price_alert_duplicate_active(
        self, user_token, user_profile, inventory_id
    ):
        r = client.post(
            "/price-alerts",
            json={"inventory_id": inventory_id, "target_price": 5.0},
            headers=_headers(user_token),
        )
        assert r.status_code == 409
        assert r.json()["detail"] == "Active alert already exists for this item"

    def test_list_price_alerts_shows_not_triggered(
        self, user_token, user_profile, inventory_id
    ):
        r = client.get("/price-alerts", headers=_headers(user_token))
        assert r.status_code == 200, r.text
        alert = next(a for a in r.json() if a["inventory_id"] == inventory_id)
        assert alert["is_triggered"] is False

    def test_update_price_alert_not_found(self, user_token, user_profile):
        fake_id = str(uuid.uuid4())
        r = client.patch(
            f"/price-alerts/{fake_id}",
            json={"target_price": 1.0},
            headers=_headers(user_token),
        )
        assert r.status_code == 404
        assert r.json()["detail"] == "Alert not found"

    def test_update_price_alert_wrong_owner(
        self, user_token, user_profile, user2_token, inventory_id
    ):
        alerts = client.get("/price-alerts", headers=_headers(user_token)).json()
        alert = next(a for a in alerts if a["inventory_id"] == inventory_id)

        r = client.patch(
            f"/price-alerts/{alert['id']}",
            json={"target_price": 1.0},
            headers=_headers(user2_token),
        )
        assert r.status_code == 404
        assert r.json()["detail"] == "Alert not found"

    def test_update_price_alert_changes_target_and_stays_watching(
        self, user_token, user_profile, inventory_id
    ):
        """inventory_id is currently priced at 10.0 (set earlier in this class)."""
        alerts = client.get("/price-alerts", headers=_headers(user_token)).json()
        alert = next(a for a in alerts if a["inventory_id"] == inventory_id)

        r = client.patch(
            f"/price-alerts/{alert['id']}",
            json={"target_price": 6.0},
            headers=_headers(user_token),
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["target_price"] == 6.0
        assert data["is_triggered"] is False

    def test_update_price_alert_triggers_when_target_meets_current_price(
        self, user_token, user_profile, inventory_id
    ):
        alerts = client.get("/price-alerts", headers=_headers(user_token)).json()
        alert = next(a for a in alerts if a["inventory_id"] == inventory_id)

        r = client.patch(
            f"/price-alerts/{alert['id']}",
            json={"target_price": 10.0},
            headers=_headers(user_token),
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["target_price"] == 10.0
        assert data["is_triggered"] is True

        # Reset back to the original target_price (5.0, set at creation) so the
        # later test_price_alert_triggers_on_price_drop (which drops the price
        # to exactly 5.0) still sees an untriggered -> triggered transition.
        r = client.patch(
            f"/price-alerts/{alert['id']}",
            json={"target_price": 5.0},
            headers=_headers(user_token),
        )
        assert r.status_code == 200, r.text
        assert r.json()["is_triggered"] is False

    def test_price_alert_triggers_on_price_drop(
        self, user_token, user_profile, store_token, store_profile, inventory_id
    ):
        r = client.put(
            f"/inventory/{inventory_id}",
            json={"price": 5.0},
            headers=_headers(store_token),
        )
        assert r.status_code == 200, r.text

        r = client.get("/price-alerts", headers=_headers(user_token))
        alert = next(a for a in r.json() if a["inventory_id"] == inventory_id)
        assert alert["is_triggered"] is True
        assert alert["current_price"] == 5.0

    def test_create_price_alert_already_met_on_creation(
        self, user_token, user_profile, store_token, store_profile, store_id
    ):
        """A target_price at/above the current price triggers immediately."""
        r = client.post(
            "/inventory/add-inventory",
            json={
                "name": "Bananas Alert Test",
                "quantity": 15,
                "category": "PRODUCE",
                "price": 2.0,
            },
            headers=_headers(store_token),
        )
        assert r.status_code == 200, r.text
        banana_id = r.json()["inventory_id"]

        r = client.post(
            "/price-alerts",
            json={"inventory_id": banana_id, "target_price": 10.0},
            headers=_headers(user_token),
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["is_triggered"] is True
        assert data["is_active"] is True

    def test_delete_price_alert_not_found(self, user_token, user_profile):
        fake_id = str(uuid.uuid4())
        r = client.delete(f"/price-alerts/{fake_id}", headers=_headers(user_token))
        assert r.status_code == 404
        assert r.json()["detail"] == "Alert not found"

    def test_delete_price_alert_success(self, user_token, user_profile, inventory_id):
        alerts = client.get("/price-alerts", headers=_headers(user_token)).json()
        alert = next(a for a in alerts if a["inventory_id"] == inventory_id)

        r = client.delete(f"/price-alerts/{alert['id']}", headers=_headers(user_token))
        assert r.status_code == 204

        alerts = client.get("/price-alerts", headers=_headers(user_token)).json()
        assert all(a["id"] != alert["id"] for a in alerts)

    def test_delete_price_alert_wrong_owner(
        self,
        user_token,
        user_profile,
        user2_token,
        store_token,
        store_profile,
        store_id,
    ):
        """An alert that exists but belongs to someone else -> 404 (not 403)."""
        r = client.post(
            "/inventory/add-inventory",
            json={
                "name": "Cherries Alert Test",
                "quantity": 5,
                "category": "PRODUCE",
                "price": 3.0,
            },
            headers=_headers(store_token),
        )
        cherry_id = r.json()["inventory_id"]
        alert = client.post(
            "/price-alerts",
            json={"inventory_id": cherry_id, "target_price": 1.0},
            headers=_headers(user_token),
        ).json()

        r = client.delete(f"/price-alerts/{alert['id']}", headers=_headers(user2_token))
        assert r.status_code == 404
        assert r.json()["detail"] == "Alert not found"


# ─────────────────────────────────────────────────────────────────────────────
# STOCK ALERTS
# ─────────────────────────────────────────────────────────────────────────────


class TestStockAlerts:

    def test_list_stock_alerts_requires_store_account(self, user2_token):
        r = client.get("/stock-alerts", headers=_headers(user2_token))
        assert r.status_code == 403
        assert r.json()["detail"] == "Store account required"

    def test_list_stock_alerts_requires_store_profile(self, noprofile_store_token):
        r = client.get("/stock-alerts", headers=_headers(noprofile_store_token))
        assert r.status_code == 400
        assert r.json()["detail"] == "Store profile not set"

    def test_acknowledge_requires_store_account(self, user2_token):
        fake_id = str(uuid.uuid4())
        r = client.post(
            f"/stock-alerts/{fake_id}/acknowledge", headers=_headers(user2_token)
        )
        assert r.status_code == 403
        assert r.json()["detail"] == "Store account required"

    def test_list_stock_alerts_empty(self, store_token, store_profile, inventory_id):
        r = client.get("/stock-alerts", headers=_headers(store_token))
        assert r.status_code == 200, r.text
        assert r.json() == []

    def test_set_threshold_and_trigger_alert(
        self, store_token, store_profile, inventory_id
    ):
        r = client.put(
            f"/inventory/{inventory_id}/threshold",
            json={"threshold": 20},
            headers=_headers(store_token),
        )
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "success"

        r = client.put(
            f"/inventory/{inventory_id}",
            json={"quantity": 10},
            headers=_headers(store_token),
        )
        assert r.status_code == 200, r.text

        r = client.get("/stock-alerts", headers=_headers(store_token))
        assert r.status_code == 200, r.text
        alerts = r.json()
        assert len(alerts) == 1
        alert = alerts[0]
        assert alert["inventory_id"] == inventory_id
        assert alert["threshold"] == 20
        assert alert["current_stock"] == 10
        assert alert["is_triggered"] is True
        assert alert["triggered_at"] is not None
        assert alert["acknowledged_at"] is None

    def test_acknowledge_alert_not_found(self, store_token, store_profile):
        fake_id = str(uuid.uuid4())
        r = client.post(
            f"/stock-alerts/{fake_id}/acknowledge", headers=_headers(store_token)
        )
        assert r.status_code == 404
        assert r.json()["detail"] == "Alert not found"

    def test_acknowledge_alert_wrong_store(
        self, store_token, store_profile, store2_token, store2_id
    ):
        alerts = client.get("/stock-alerts", headers=_headers(store_token)).json()
        alert_id = alerts[0]["id"]

        r = client.post(
            f"/stock-alerts/{alert_id}/acknowledge", headers=_headers(store2_token)
        )
        assert r.status_code == 403
        assert r.json()["detail"] == "Not your inventory"

    def test_acknowledge_alert_success(self, store_token, store_profile, inventory_id):
        alerts = client.get("/stock-alerts", headers=_headers(store_token)).json()
        alert = next(a for a in alerts if a["inventory_id"] == inventory_id)

        r = client.post(
            f"/stock-alerts/{alert['id']}/acknowledge", headers=_headers(store_token)
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["is_triggered"] is False
        assert data["acknowledged_at"] is not None

        alerts = client.get("/stock-alerts", headers=_headers(store_token)).json()
        updated = next(a for a in alerts if a["inventory_id"] == inventory_id)
        assert updated["is_triggered"] is False
        assert updated["acknowledged_at"] is not None
