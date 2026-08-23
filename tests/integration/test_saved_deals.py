"""
Integration tests for saved deals / My Deals (SPEC_SAVED_DEALS.md).

Covers api/saved_deal_api.py: POST/DELETE /feed/{id}/save, GET
/feed/{id}/saved, GET /my-deals.

Uses its own dedicated user/store fixtures, mirroring
tests/integration/test_store_feed.py's isolation approach.
"""
import uuid
from datetime import date, datetime, timedelta

import pytest

from tests.integration.helpers import _headers, _login, _otp_and_verify, _register, client

_suffix = str(uuid.uuid4().int)[:6]
DEAL_USER_PHONE = f"+1577{_suffix}01"
DEAL_STORE_PHONE = f"+1577{_suffix}02"


@pytest.fixture(scope="module")
def deal_user_token():
    _otp_and_verify(DEAL_USER_PHONE)
    _register(DEAL_USER_PHONE, "user")
    token = _login(DEAL_USER_PHONE)
    r = client.post(
        "/user/set-profile",
        json={"name": "Deal Shopper", "email": "dealshopper@groceror.test", "location": "Deal City"},
        headers=_headers(token),
    )
    assert r.status_code == 200, r.text
    return token


@pytest.fixture(scope="module")
def deal_store_token():
    _otp_and_verify(DEAL_STORE_PHONE)
    _register(DEAL_STORE_PHONE, "store")
    return _login(DEAL_STORE_PHONE)


@pytest.fixture(scope="module")
def deal_store_id(deal_store_token):
    r = client.post(
        "/stores/",
        json={
            "name": "Deal Grocer", "email": "dealgrocer@groceror.test",
            "website": "https://dealgrocer.test", "location": "1 Deal St",
        },
        headers=_headers(deal_store_token),
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


@pytest.fixture(scope="module")
def deal_store_profile(deal_store_token, deal_store_id):
    r = client.post(
        "/user/set-profile",
        json={
            "name": "Deal Grocer", "email": "dealgrocer@groceror.test",
            "website": "https://dealgrocer.test", "location": "1 Deal St",
        },
        headers=_headers(deal_store_token),
    )
    assert r.status_code == 200, r.text
    return {}


@pytest.fixture(scope="module")
def deal_inventory_id(deal_store_token, deal_store_id, deal_store_profile):
    r = client.post(
        "/inventory/add-inventory",
        json={"name": "Deal Eggs", "quantity": 20, "category": "DAIRY", "price": 10.0},
        headers=_headers(deal_store_token),
    )
    assert r.status_code == 200, r.text
    return r.json()["inventory_id"]


@pytest.fixture(scope="module")
def deal_followed(deal_user_token, deal_store_id, deal_store_profile):
    r = client.post(f"/stores/{deal_store_id}/follow", headers=_headers(deal_user_token))
    assert r.status_code == 200, r.text
    return True


def _find_post(store_id, headers, update_type, ref_id=None):
    updates = client.get(f"/stores/{store_id}/updates?limit=100", headers=headers)
    assert updates.status_code == 200, updates.text
    items = [i for i in updates.json()["items"] if i["update_type"] == update_type]
    if ref_id is not None:
        items = [i for i in items if i["ref_id"] == ref_id]
    assert items, f"no {update_type} feed post found"
    return items[0]


@pytest.fixture(scope="module")
def coupon_feed_post(deal_store_token, deal_store_id, deal_store_profile):
    code = f"SAVE{_suffix}"
    r = client.post(
        "/coupons",
        json={"code": code, "discount_type": "percent", "discount_value": 15},
        headers=_headers(deal_store_token),
    )
    assert r.status_code == 201, r.text
    coupon_id = r.json()["id"]
    return _find_post(deal_store_id, _headers(deal_store_token), "coupon", coupon_id)


@pytest.fixture(scope="module")
def promotion_feed_post(deal_store_token, deal_store_id, deal_store_profile, deal_inventory_id):
    r = client.post(
        f"/inventory/{deal_inventory_id}/promotion",
        json={
            "sale_price": 7.0,
            "start_date": str(date.today()),
            "end_date": str(date.today() + timedelta(days=7)),
        },
        headers=_headers(deal_store_token),
    )
    assert r.status_code == 200, r.text
    return _find_post(deal_store_id, _headers(deal_store_token), "promotion")


@pytest.fixture(scope="module")
def flash_sale_feed_post(deal_store_token, deal_store_id, deal_store_profile, deal_inventory_id):
    start_at = (datetime.utcnow() - timedelta(minutes=1)).isoformat() + "Z"
    end_at = (datetime.utcnow() + timedelta(hours=1)).isoformat() + "Z"
    r = client.post(
        "/flash-sales",
        json={"inventory_id": deal_inventory_id, "sale_price": 4.5, "start_at": start_at, "end_at": end_at},
        headers=_headers(deal_store_token),
    )
    assert r.status_code == 200, r.text
    sale_id = r.json()["id"]
    return _find_post(deal_store_id, _headers(deal_store_token), "flash_sale", sale_id)


@pytest.fixture(scope="module")
def announcement_feed_post(deal_store_token, deal_store_profile):
    r = client.post(
        "/stores/updates", json={"message": "Not a deal, just an announcement"},
        headers=_headers(deal_store_token),
    )
    assert r.status_code == 201, r.text
    return r.json()


class TestSaveDeal:

    def test_save_requires_profile(self, deal_store_token, coupon_feed_post):
        r = client.post(f"/feed/{coupon_feed_post['id']}/save", headers=_headers(deal_store_token))
        # deal_store_token has no shopper User profile — same "User profile not set" gate
        assert r.status_code == 400

    def test_save_not_found(self, deal_user_token):
        fake_id = str(uuid.uuid4())
        r = client.post(f"/feed/{fake_id}/save", headers=_headers(deal_user_token))
        assert r.status_code == 404

    def test_save_rejects_announcement(self, deal_user_token, announcement_feed_post):
        r = client.post(f"/feed/{announcement_feed_post['id']}/save", headers=_headers(deal_user_token))
        assert r.status_code == 400

    def test_save_coupon(self, deal_user_token, coupon_feed_post):
        r = client.post(f"/feed/{coupon_feed_post['id']}/save", headers=_headers(deal_user_token))
        assert r.status_code == 201, r.text
        data = r.json()
        assert data["update_type"] == "coupon"
        assert data["status"] == "active"
        assert data["code"] is not None
        assert data["sale_price"] is None

    def test_save_is_idempotent(self, deal_user_token, coupon_feed_post):
        first = client.post(f"/feed/{coupon_feed_post['id']}/save", headers=_headers(deal_user_token))
        second = client.post(f"/feed/{coupon_feed_post['id']}/save", headers=_headers(deal_user_token))
        assert first.status_code == 201
        assert second.status_code == 201
        assert first.json()["id"] == second.json()["id"]

    def test_save_promotion(self, deal_user_token, promotion_feed_post):
        r = client.post(f"/feed/{promotion_feed_post['id']}/save", headers=_headers(deal_user_token))
        assert r.status_code == 201, r.text
        data = r.json()
        assert data["update_type"] == "promotion"
        assert data["sale_price"] == 7.0
        assert data["code"] is None

    def test_save_flash_sale(self, deal_user_token, flash_sale_feed_post):
        r = client.post(f"/feed/{flash_sale_feed_post['id']}/save", headers=_headers(deal_user_token))
        assert r.status_code == 201, r.text
        data = r.json()
        assert data["update_type"] == "flash_sale"
        assert data["status"] == "active"
        assert data["expires_at"] is not None

    def test_check_saved(self, deal_user_token, coupon_feed_post):
        r = client.get(f"/feed/{coupon_feed_post['id']}/saved", headers=_headers(deal_user_token))
        assert r.status_code == 200
        assert r.json() is True

    def test_check_not_saved(self, deal_user_token):
        fake_id = str(uuid.uuid4())
        r = client.get(f"/feed/{fake_id}/saved", headers=_headers(deal_user_token))
        assert r.status_code == 200
        assert r.json() is False


class TestMyDeals:

    def test_my_deals_requires_profile(self, deal_store_token):
        r = client.get("/my-deals", headers=_headers(deal_store_token))
        assert r.status_code == 400

    def test_my_deals_lists_saved_items(
        self, deal_user_token, coupon_feed_post, promotion_feed_post, flash_sale_feed_post
    ):
        # ensure all three are saved (earlier tests already save coupon/promo/flash_sale)
        for post in (coupon_feed_post, promotion_feed_post, flash_sale_feed_post):
            client.post(f"/feed/{post['id']}/save", headers=_headers(deal_user_token))

        r = client.get("/my-deals", headers=_headers(deal_user_token))
        assert r.status_code == 200, r.text
        items = r.json()["items"]
        types = {i["update_type"] for i in items}
        assert {"coupon", "promotion", "flash_sale"} <= types

    def test_my_deals_active_before_expired(self, deal_user_token, coupon_feed_post):
        r = client.get("/my-deals", headers=_headers(deal_user_token))
        statuses = [i["status"] for i in r.json()["items"]]
        # no "expired" entries should appear before an "active"/"upcoming" one
        if "expired" in statuses:
            first_expired = statuses.index("expired")
            assert all(s != "expired" for s in statuses[:first_expired])


class TestUnsaveDeal:

    def test_unsave_removes_from_my_deals(self, deal_user_token, coupon_feed_post):
        client.post(f"/feed/{coupon_feed_post['id']}/save", headers=_headers(deal_user_token))

        r = client.delete(f"/feed/{coupon_feed_post['id']}/save", headers=_headers(deal_user_token))
        assert r.status_code == 204

        check = client.get(f"/feed/{coupon_feed_post['id']}/saved", headers=_headers(deal_user_token))
        assert check.json() is False

        deals = client.get("/my-deals", headers=_headers(deal_user_token))
        assert coupon_feed_post["id"] not in [i["feed_post_id"] for i in deals.json()["items"]]

    def test_unsave_nonexistent_is_noop(self, deal_user_token):
        fake_id = str(uuid.uuid4())
        r = client.delete(f"/feed/{fake_id}/save", headers=_headers(deal_user_token))
        assert r.status_code == 204
