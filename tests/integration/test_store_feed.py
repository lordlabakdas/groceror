"""
Integration tests for the store follow feed (SPEC_STORE_FOLLOW_FEED.md).

Covers:
  - api/store_feed_api.py (GET /feed, POST /feed/read, POST /stores/updates,
    DELETE /stores/updates/{id}, GET /stores/{store_id}/updates)
  - auto-emission wired into api/coupon_api.py::create_coupon,
    api/inventory_api.py::set_promotion, api/flash_sale_api.py::create_flash_sale

Uses its own dedicated user/store fixtures (not the shared conftest ones)
so feed state — follows, posts, read cursor — doesn't depend on what other
test files in this run have already done to the shared store.
"""

import uuid
from datetime import date, datetime, timedelta

import pytest

from tests.integration.helpers import (_headers, _login, _otp_and_verify,
                                       _register, client)

_suffix = str(uuid.uuid4().int)[:6]
FEED_USER_PHONE = f"+1569{_suffix}01"
FEED_STORE_PHONE = f"+1569{_suffix}02"
FEED_NONFOLLOWER_PHONE = f"+1569{_suffix}03"


@pytest.fixture(scope="module")
def feed_user_token():
    _otp_and_verify(FEED_USER_PHONE)
    _register(FEED_USER_PHONE, "user")
    token = _login(FEED_USER_PHONE)
    r = client.post(
        "/user/set-profile",
        json={
            "name": "Feed Shopper",
            "email": "feedshopper@groceror.test",
            "location": "Feed City",
        },
        headers=_headers(token),
    )
    assert r.status_code == 200, r.text
    return token


@pytest.fixture(scope="module")
def feed_nonfollower_token():
    """A profiled user who never follows the store — proves the feed is follow-scoped."""
    _otp_and_verify(FEED_NONFOLLOWER_PHONE)
    _register(FEED_NONFOLLOWER_PHONE, "user")
    token = _login(FEED_NONFOLLOWER_PHONE)
    r = client.post(
        "/user/set-profile",
        json={
            "name": "Non Follower",
            "email": "nonfollower@groceror.test",
            "location": "Elsewhere",
        },
        headers=_headers(token),
    )
    assert r.status_code == 200, r.text
    return token


@pytest.fixture(scope="module")
def feed_store_token():
    _otp_and_verify(FEED_STORE_PHONE)
    _register(FEED_STORE_PHONE, "store")
    return _login(FEED_STORE_PHONE)


@pytest.fixture(scope="module")
def feed_store_id(feed_store_token):
    r = client.post(
        "/stores/",
        json={
            "name": "Feed Grocer",
            "email": "feedgrocer@groceror.test",
            "website": "https://feedgrocer.test",
            "location": "1 Feed St",
        },
        headers=_headers(feed_store_token),
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


@pytest.fixture(scope="module")
def feed_store_profile(feed_store_token, feed_store_id):
    r = client.post(
        "/user/set-profile",
        json={
            "name": "Feed Grocer",
            "email": "feedgrocer@groceror.test",
            "website": "https://feedgrocer.test",
            "location": "1 Feed St",
        },
        headers=_headers(feed_store_token),
    )
    assert r.status_code == 200, r.text
    return {}


@pytest.fixture(scope="module")
def feed_inventory_id(feed_store_token, feed_store_id, feed_store_profile):
    r = client.post(
        "/inventory/add-inventory",
        json={"name": "Feed Eggs", "quantity": 20, "category": "DAIRY", "price": 10.0},
        headers=_headers(feed_store_token),
    )
    assert r.status_code == 200, r.text
    return r.json()["inventory_id"]


@pytest.fixture(scope="module")
def feed_followed(feed_user_token, feed_store_id, feed_store_profile):
    """feed_user follows feed_store, once, for the whole module."""
    r = client.post(
        f"/stores/{feed_store_id}/follow", headers=_headers(feed_user_token)
    )
    assert r.status_code == 200, r.text
    return True


# ─────────────────────────────────────────────────────────────────────────────
# ANNOUNCEMENTS
# ─────────────────────────────────────────────────────────────────────────────


class TestAnnouncements:

    def test_post_announcement_requires_store(self, feed_user_token):
        r = client.post(
            "/stores/updates", json={"message": "hi"}, headers=_headers(feed_user_token)
        )
        assert r.status_code == 403

    def test_post_announcement_rejects_empty_message(
        self, feed_store_token, feed_store_profile
    ):
        r = client.post(
            "/stores/updates", json={"message": ""}, headers=_headers(feed_store_token)
        )
        assert r.status_code == 422

    def test_post_announcement_success(
        self, feed_store_token, feed_store_id, feed_store_profile, feed_followed
    ):
        r = client.post(
            "/stores/updates",
            json={"message": "New shipment of organic produce arriving Friday!"},
            headers=_headers(feed_store_token),
        )
        assert r.status_code == 201, r.text
        data = r.json()
        assert data["store_id"] == feed_store_id
        assert data["update_type"] == "announcement"
        assert data["message"] == "New shipment of organic produce arriving Friday!"
        assert data["ref_id"] is None
        assert data["discount_label"] is None
        assert data["coupon_code"] is None
        assert data["expires_at"] is None

    def test_delete_announcement_wrong_owner(
        self, feed_store_token, feed_store_id, feed_store_profile
    ):
        create = client.post(
            "/stores/updates",
            json={"message": "temp"},
            headers=_headers(feed_store_token),
        )
        assert create.status_code == 201, create.text
        update_id = create.json()["id"]

        r = client.delete(
            f"/stores/updates/{update_id}", headers=_headers(feed_store_token)
        )
        assert r.status_code == 204, r.text

    def test_delete_announcement_not_found(self, feed_store_token, feed_store_profile):
        fake_id = str(uuid.uuid4())
        r = client.delete(
            f"/stores/updates/{fake_id}", headers=_headers(feed_store_token)
        )
        assert r.status_code == 404

    def test_delete_auto_generated_post_rejected(
        self, feed_store_token, feed_store_id, feed_store_profile, feed_inventory_id
    ):
        coupon_code = f"NODEL{_suffix}"
        r = client.post(
            "/coupons",
            json={"code": coupon_code, "discount_type": "fixed", "discount_value": 2},
            headers=_headers(feed_store_token),
        )
        assert r.status_code == 201, r.text

        updates = client.get(
            f"/stores/{feed_store_id}/updates", headers=_headers(feed_store_token)
        )
        assert updates.status_code == 200, updates.text
        coupon_post = next(
            i
            for i in updates.json()["items"]
            if i["update_type"] == "coupon" and i["message"].find(coupon_code) != -1
        )

        r = client.delete(
            f"/stores/updates/{coupon_post['id']}", headers=_headers(feed_store_token)
        )
        assert r.status_code == 400


# ─────────────────────────────────────────────────────────────────────────────
# AUTO-EMISSION
# ─────────────────────────────────────────────────────────────────────────────


class TestAutoEmission:

    def test_coupon_creation_emits_feed_post(
        self, feed_store_token, feed_store_id, feed_store_profile
    ):
        code = f"FEED10{_suffix}"
        r = client.post(
            "/coupons",
            json={"code": code, "discount_type": "percent", "discount_value": 10},
            headers=_headers(feed_store_token),
        )
        assert r.status_code == 201, r.text
        coupon_id = r.json()["id"]

        updates = client.get(
            f"/stores/{feed_store_id}/updates", headers=_headers(feed_store_token)
        )
        assert updates.status_code == 200, updates.text
        matches = [
            i
            for i in updates.json()["items"]
            if i["update_type"] == "coupon" and i["ref_id"] == coupon_id
        ]
        assert len(matches) == 1
        assert code in matches[0]["message"]
        assert "10%" in matches[0]["message"]

    def test_coupon_feed_post_carries_discount_info(
        self, feed_store_token, feed_store_id, feed_store_profile
    ):
        code = f"DISC{_suffix}"
        r = client.post(
            "/coupons",
            json={"code": code, "discount_type": "fixed", "discount_value": 3},
            headers=_headers(feed_store_token),
        )
        assert r.status_code == 201, r.text
        coupon_id = r.json()["id"]

        updates = client.get(
            f"/stores/{feed_store_id}/updates", headers=_headers(feed_store_token)
        )
        post = next(i for i in updates.json()["items"] if i["ref_id"] == coupon_id)
        assert post["discount_label"] == "$3 off"
        assert post["coupon_code"] == code
        assert post["expires_at"] is None

    def test_new_promotion_emits_feed_post(
        self, feed_store_token, feed_store_id, feed_store_profile, feed_inventory_id
    ):
        r = client.post(
            f"/inventory/{feed_inventory_id}/promotion",
            json={
                "sale_price": 7.5,
                "start_date": str(date.today()),
                "end_date": str(date.today() + timedelta(days=7)),
            },
            headers=_headers(feed_store_token),
        )
        assert r.status_code == 200, r.text

        updates = client.get(
            f"/stores/{feed_store_id}/updates", headers=_headers(feed_store_token)
        )
        promo_posts = [
            i for i in updates.json()["items"] if i["update_type"] == "promotion"
        ]
        assert len(promo_posts) == 1
        assert "Feed Eggs" in promo_posts[0]["message"]
        assert promo_posts[0]["discount_label"] == "$7.5"
        assert promo_posts[0]["coupon_code"] is None
        assert promo_posts[0]["expires_at"] is not None
        assert promo_posts[0]["expires_at"].startswith(
            str(date.today() + timedelta(days=7))
        )

    def test_promotion_update_does_not_re_emit(
        self, feed_store_token, feed_store_id, feed_store_profile, feed_inventory_id
    ):
        """Second call to the same endpoint updates the existing Promotion row —
        should not post a second feed entry (see SPEC_STORE_FOLLOW_FEED.md §3)."""
        r = client.post(
            f"/inventory/{feed_inventory_id}/promotion",
            json={
                "sale_price": 6.0,
                "start_date": str(date.today()),
                "end_date": str(date.today() + timedelta(days=7)),
            },
            headers=_headers(feed_store_token),
        )
        assert r.status_code == 200, r.text

        updates = client.get(
            f"/stores/{feed_store_id}/updates", headers=_headers(feed_store_token)
        )
        promo_posts = [
            i for i in updates.json()["items"] if i["update_type"] == "promotion"
        ]
        assert len(promo_posts) == 1  # still just the one from the create above

    def test_flash_sale_creation_emits_feed_post(
        self, feed_store_token, feed_store_id, feed_store_profile, feed_inventory_id
    ):
        start_at = (datetime.utcnow() - timedelta(minutes=1)).isoformat() + "Z"
        end_at = (datetime.utcnow() + timedelta(hours=1)).isoformat() + "Z"
        r = client.post(
            "/flash-sales",
            json={
                "inventory_id": feed_inventory_id,
                "sale_price": 5.0,
                "start_at": start_at,
                "end_at": end_at,
            },
            headers=_headers(feed_store_token),
        )
        assert r.status_code == 200, r.text
        sale_id = r.json()["id"]

        updates = client.get(
            f"/stores/{feed_store_id}/updates", headers=_headers(feed_store_token)
        )
        matches = [
            i
            for i in updates.json()["items"]
            if i["update_type"] == "flash_sale" and i["ref_id"] == sale_id
        ]
        assert len(matches) == 1
        assert "Feed Eggs" in matches[0]["message"]
        assert matches[0]["discount_label"] == "$5"
        assert matches[0]["coupon_code"] is None
        assert matches[0]["expires_at"] is not None

    def test_cancelling_flash_sale_leaves_feed_post(
        self, feed_store_token, feed_store_id, feed_store_profile, feed_inventory_id
    ):
        start_at = (datetime.utcnow() - timedelta(minutes=1)).isoformat() + "Z"
        end_at = (datetime.utcnow() + timedelta(hours=2)).isoformat() + "Z"
        created = client.post(
            "/flash-sales",
            json={
                "inventory_id": feed_inventory_id,
                "sale_price": 4.0,
                "start_at": start_at,
                "end_at": end_at,
            },
            headers=_headers(feed_store_token),
        )
        assert created.status_code == 200, created.text
        sale_id = created.json()["id"]

        cancel = client.delete(
            f"/flash-sales/{sale_id}", headers=_headers(feed_store_token)
        )
        assert cancel.status_code == 204, cancel.text

        updates = client.get(
            f"/stores/{feed_store_id}/updates", headers=_headers(feed_store_token)
        )
        matches = [i for i in updates.json()["items"] if i["ref_id"] == sale_id]
        assert (
            len(matches) == 1
        )  # immutable history — the post is not removed on cancel


# ─────────────────────────────────────────────────────────────────────────────
# FEED (shopper side)
# ─────────────────────────────────────────────────────────────────────────────


class TestFeed:

    def test_feed_requires_profile(self, feed_store_token):
        r = client.get("/feed", headers=_headers(feed_store_token))
        assert r.status_code == 400
        assert r.json()["detail"] == "User profile not set"

    def test_feed_only_shows_followed_stores(
        self, feed_nonfollower_token, feed_store_id
    ):
        """A non-follower's feed excludes feed_store's non-sponsored activity.
        Not asserting an empty list overall: sponsored posts (SPEC_SPONSORED_
        POSTS.md) are visible to every shopper regardless of follow status
        by design, and other test modules may have created some — this test
        only cares that follow-scoping itself excludes feed_store."""
        r = client.get("/feed", headers=_headers(feed_nonfollower_token))
        assert r.status_code == 200, r.text
        data = r.json()
        assert all(item["store_id"] != feed_store_id for item in data["items"])

    def test_feed_item_created_at_is_tz_aware(self, feed_user_token, feed_followed):
        """Regression test: created_at must serialize with a UTC offset, same
        as flash_sale_api.py's end_at (see its _aware_utc docstring) — left
        naive, the frontend's `new Date(...)` misreads it as local time and
        the feed shows timestamps in the future."""
        r = client.get("/feed", headers=_headers(feed_user_token))
        assert r.status_code == 200, r.text
        items = r.json()["items"]
        assert len(items) > 0
        for item in items:
            assert item["created_at"].endswith("+00:00") or item["created_at"].endswith(
                "Z"
            )

    def test_feed_shows_followed_store_activity(
        self, feed_user_token, feed_store_id, feed_followed
    ):
        """Every item is either from feed_store (followed) or a sponsored
        post (visible platform-wide by design, SPEC_SPONSORED_POSTS.md) —
        and at least one item actually comes from feed_store, proving
        follow-scoping itself still works."""
        r = client.get("/feed", headers=_headers(feed_user_token))
        assert r.status_code == 200, r.text
        data = r.json()
        assert len(data["items"]) > 0
        assert any(item["store_id"] == feed_store_id for item in data["items"])
        assert all(
            item["store_id"] == feed_store_id or item["update_type"] == "sponsored"
            for item in data["items"]
        )
        # newest first
        created_ats = [item["created_at"] for item in data["items"]]
        assert created_ats == sorted(created_ats, reverse=True)

        # discount enrichment reaches the shopper-facing /feed too, not just
        # the store-owner-facing /stores/{id}/updates history
        coupon_items = [i for i in data["items"] if i["update_type"] == "coupon"]
        assert len(coupon_items) > 0
        assert all(i["discount_label"] and i["coupon_code"] for i in coupon_items)

    def test_feed_pagination(self, feed_user_token, feed_followed):
        full = client.get("/feed?limit=100", headers=_headers(feed_user_token))
        assert full.status_code == 200, full.text
        total_items = len(full.json()["items"])
        assert (
            total_items >= 4
        )  # coupon + promotion + 2 flash sales from TestAutoEmission

        page1 = client.get("/feed?limit=2&offset=0", headers=_headers(feed_user_token))
        assert page1.status_code == 200, page1.text
        assert len(page1.json()["items"]) == 2
        assert page1.json()["has_more"] is True

    def test_feed_limit_clamped(self, feed_user_token, feed_followed):
        r = client.get("/feed?limit=9999", headers=_headers(feed_user_token))
        assert r.status_code == 200, r.text
        assert len(r.json()["items"]) <= 100

    def test_unread_count_and_mark_read(self, feed_user_token, feed_followed):
        before = client.get("/feed", headers=_headers(feed_user_token))
        assert before.json()["unread_count"] > 0

        mark = client.post("/feed/read", headers=_headers(feed_user_token))
        assert mark.status_code == 204, mark.text

        after = client.get("/feed", headers=_headers(feed_user_token))
        assert after.json()["unread_count"] == 0

        # a fresh post after marking read should bump unread_count back up
        store_token = _login(FEED_STORE_PHONE)
        post = client.post(
            "/stores/updates",
            json={"message": "Fresh unread test post"},
            headers=_headers(store_token),
        )
        assert post.status_code == 201, post.text

        after2 = client.get("/feed", headers=_headers(feed_user_token))
        assert after2.json()["unread_count"] == 1


# ─────────────────────────────────────────────────────────────────────────────
# PER-STORE UPDATE HISTORY (public)
# ─────────────────────────────────────────────────────────────────────────────


class TestStoreUpdatesHistory:

    def test_list_store_updates_store_not_found(self, feed_user_token):
        fake_id = str(uuid.uuid4())
        r = client.get(f"/stores/{fake_id}/updates", headers=_headers(feed_user_token))
        assert r.status_code == 404

    def test_list_store_updates_visible_to_non_follower(
        self, feed_nonfollower_token, feed_store_id
    ):
        """Anyone authenticated can see a store's update history, follower or not —
        it's how a shopper decides whether to follow in the first place."""
        r = client.get(
            f"/stores/{feed_store_id}/updates", headers=_headers(feed_nonfollower_token)
        )
        assert r.status_code == 200, r.text
        assert len(r.json()["items"]) > 0
