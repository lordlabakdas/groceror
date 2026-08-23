"""
Integration tests for sponsored posts (SPEC_SPONSORED_POSTS.md).

Covers api/sponsored_post_api.py (POST /stores/sponsored-posts, POST
/stores/sponsored-posts/{id}/confirm, GET /stores/sponsored-posts,
GET|POST /sponsored-posts/admin/price) and the store_feed_service broadening
that lets a "sponsored" StoreFeedPost reach shoppers who don't follow the
store — the core claim this feature makes.

Uses FakeBillingProvider throughout, same posture as
test_subscription_billing.py — no live Razorpay calls under test.
"""
import uuid
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from sqlmodel import select

from config import AdminConfig
from engine.billing.fake_provider import VALID_PAYMENT_SIGNATURE, FakeBillingProvider
from models.db import db_session
from models.entity.sponsored_post_pricing_entity import SponsoredPostPricing
from models.entity.subscription_entity import Subscription
from models.service import subscription_service
from tests.integration.helpers import _headers, _login, _otp_and_verify, _register, client

_suffix = str(uuid.uuid4().int)[:6]
ADMIN_HEADERS = {"x-admin-token": AdminConfig.ADMIN_TOKEN}

SP_STORE_PHONE = f"+1583{_suffix}01"
SP_FOLLOWER_PHONE = f"+1583{_suffix}02"
SP_NONFOLLOWER_PHONE = f"+1583{_suffix}03"


@pytest.fixture(scope="module", autouse=True)
def seeded_price():
    """The real deploy seeds this via the Alembic migration
    (e2f3a4b5c6d7); the SQLite test DB only gets create_all()."""
    price = SponsoredPostPricing(price_paise=19900, created_by="test-seed")
    db_session.add(price)
    db_session.commit()
    return price


@pytest.fixture(scope="module")
def sp_store_token():
    _otp_and_verify(SP_STORE_PHONE)
    _register(SP_STORE_PHONE, "store")
    return _login(SP_STORE_PHONE)


@pytest.fixture(scope="module")
def sp_store_id(sp_store_token):
    r = client.post(
        "/stores/",
        json={
            "name": "Sponsored Grocer", "email": "sponsoredgrocer@groceror.test",
            "website": "https://sponsoredgrocer.test", "location": "1 Ad St",
        },
        headers=_headers(sp_store_token),
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


@pytest.fixture(scope="module")
def sp_follower_token():
    _otp_and_verify(SP_FOLLOWER_PHONE)
    _register(SP_FOLLOWER_PHONE, "user")
    token = _login(SP_FOLLOWER_PHONE)
    r = client.post(
        "/user/set-profile",
        json={"name": "Sponsored Follower", "email": "spfollower@groceror.test", "location": "City"},
        headers=_headers(token),
    )
    assert r.status_code == 200, r.text
    return token


@pytest.fixture(scope="module")
def sp_nonfollower_token():
    """Never follows sp_store — proves a sponsored post still reaches them."""
    _otp_and_verify(SP_NONFOLLOWER_PHONE)
    _register(SP_NONFOLLOWER_PHONE, "user")
    token = _login(SP_NONFOLLOWER_PHONE)
    r = client.post(
        "/user/set-profile",
        json={"name": "Sponsored Non-Follower", "email": "spnonfollower@groceror.test", "location": "Elsewhere"},
        headers=_headers(token),
    )
    assert r.status_code == 200, r.text
    return token


@pytest.fixture(scope="module")
def sp_followed(sp_follower_token, sp_store_id):
    r = client.post(f"/stores/{sp_store_id}/follow", headers=_headers(sp_follower_token))
    assert r.status_code == 200, r.text
    return True


def _create_pending(store_token, fake_provider, message="Grand opening! 20% off everything."):
    with patch("models.service.sponsored_post_service.get_billing_provider", return_value=fake_provider):
        r = client.post("/stores/sponsored-posts", json={"message": message}, headers=_headers(store_token))
    assert r.status_code == 201, r.text
    return r.json()


def _confirm(store_token, fake_provider, sponsored_post_id, order_id, signature=VALID_PAYMENT_SIGNATURE, payment_id="fake_pay_1"):
    with patch("models.service.sponsored_post_service.get_billing_provider", return_value=fake_provider):
        return client.post(
            f"/stores/sponsored-posts/{sponsored_post_id}/confirm",
            json={"razorpay_payment_id": payment_id, "razorpay_order_id": order_id, "razorpay_signature": signature},
            headers=_headers(store_token),
        )


class TestCreateSponsoredPost:

    def test_create_requires_store(self, sp_follower_token):
        r = client.post("/stores/sponsored-posts", json={"message": "hi"}, headers=_headers(sp_follower_token))
        assert r.status_code == 403

    def test_create_rejects_empty_message(self, sp_store_token, sp_store_id):
        r = client.post("/stores/sponsored-posts", json={"message": ""}, headers=_headers(sp_store_token))
        assert r.status_code == 422

    def test_create_pending_returns_order(self, sp_store_token, sp_store_id):
        fake_provider = FakeBillingProvider()
        data = _create_pending(sp_store_token, fake_provider)
        assert data["amount_paise"] == 19900
        assert data["razorpay_order_id"] in fake_provider.orders

    def test_create_blocked_when_billing_locked(self, sp_store_token, sp_store_id):
        sub = db_session.exec(select(Subscription).where(Subscription.store_id == uuid.UUID(sp_store_id))).first()
        sub.status = "grace"
        sub.grace_period_end = datetime.utcnow() - timedelta(days=1)  # already expired
        db_session.add(sub)
        db_session.commit()

        # Trigger the lazy recompute (SPEC_SUBSCRIPTION.md §3.2) -> locked.
        client.get("/subscription/status", headers=_headers(sp_store_token))

        fake_provider = FakeBillingProvider()
        with patch("models.service.sponsored_post_service.get_billing_provider", return_value=fake_provider):
            r = client.post("/stores/sponsored-posts", json={"message": "should fail"}, headers=_headers(sp_store_token))
        assert r.status_code == 402

        # Unlock again so later tests in this module aren't affected.
        subscription_service.admin_unlock(uuid.UUID(sp_store_id))


class TestConfirmSponsoredPost:

    def test_confirm_missing_post(self, sp_store_token):
        fake_id = str(uuid.uuid4())
        fake_provider = FakeBillingProvider()
        r = _confirm(sp_store_token, fake_provider, fake_id, "order_x")
        assert r.status_code == 404

    def test_confirm_order_mismatch(self, sp_store_token):
        fake_provider = FakeBillingProvider()
        data = _create_pending(sp_store_token, fake_provider)
        r = _confirm(sp_store_token, fake_provider, data["sponsored_post_id"], "wrong_order_id")
        assert r.status_code == 400

    def test_confirm_invalid_signature_marks_failed_and_stays_hidden(self, sp_store_token, sp_nonfollower_token):
        fake_provider = FakeBillingProvider()
        data = _create_pending(sp_store_token, fake_provider, message="Should never be seen anywhere")
        r = _confirm(sp_store_token, fake_provider, data["sponsored_post_id"], data["razorpay_order_id"], signature="not-the-real-signature")
        assert r.status_code == 400

        feed = client.get("/feed", headers=_headers(sp_nonfollower_token))
        messages = [i["message"] for i in feed.json()["items"]]
        assert "Should never be seen anywhere" not in messages

    def test_confirm_success_creates_feed_post(self, sp_store_token, sp_store_id):
        fake_provider = FakeBillingProvider()
        data = _create_pending(sp_store_token, fake_provider, message="Sponsored: fresh produce sale")
        r = _confirm(sp_store_token, fake_provider, data["sponsored_post_id"], data["razorpay_order_id"])
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["update_type"] == "sponsored"
        assert body["message"] == "Sponsored: fresh produce sale"
        assert body["store_id"] == sp_store_id

    def test_confirm_twice_conflicts(self, sp_store_token):
        fake_provider = FakeBillingProvider()
        data = _create_pending(sp_store_token, fake_provider)
        first = _confirm(sp_store_token, fake_provider, data["sponsored_post_id"], data["razorpay_order_id"])
        assert first.status_code == 200, first.text
        second = _confirm(sp_store_token, fake_provider, data["sponsored_post_id"], data["razorpay_order_id"])
        assert second.status_code == 409


class TestSponsoredReachesNonFollowers:

    def test_nonfollower_sees_sponsored_but_not_announcement(self, sp_store_token, sp_nonfollower_token):
        ann = client.post(
            "/stores/updates", json={"message": "Followers-only announcement"}, headers=_headers(sp_store_token)
        )
        assert ann.status_code == 201, ann.text

        fake_provider = FakeBillingProvider()
        data = _create_pending(sp_store_token, fake_provider, message="Reach everyone sponsored post")
        confirmed = _confirm(sp_store_token, fake_provider, data["sponsored_post_id"], data["razorpay_order_id"])
        assert confirmed.status_code == 200, confirmed.text

        feed = client.get("/feed", headers=_headers(sp_nonfollower_token))
        messages = [i["message"] for i in feed.json()["items"]]
        assert "Reach everyone sponsored post" in messages
        assert "Followers-only announcement" not in messages

    def test_follower_sees_sponsored_too(self, sp_follower_token, sp_followed):
        feed = client.get("/feed", headers=_headers(sp_follower_token))
        types = {i["update_type"] for i in feed.json()["items"]}
        assert "sponsored" in types

    def test_store_own_history_shows_sponsored(self, sp_store_id, sp_nonfollower_token):
        r = client.get(f"/stores/{sp_store_id}/updates", headers=_headers(sp_nonfollower_token))
        assert any(i["update_type"] == "sponsored" for i in r.json()["items"])


class TestSpendHistory:

    def test_list_own_spend(self, sp_store_token):
        r = client.get("/stores/sponsored-posts", headers=_headers(sp_store_token))
        assert r.status_code == 200, r.text
        items = r.json()["items"]
        assert any(i["status"] == "paid" for i in items)
        assert any(i["status"] == "failed" for i in items)


class TestAdminPricing:

    def test_admin_endpoints_require_token(self):
        r = client.get("/sponsored-posts/admin/price")
        assert r.status_code == 422  # required Header(...) 422s before _require_admin runs

        r = client.get("/sponsored-posts/admin/price", headers={"x-admin-token": "wrong"})
        assert r.status_code == 403

    def test_get_price(self):
        r = client.get("/sponsored-posts/admin/price", headers=ADMIN_HEADERS)
        assert r.status_code == 200, r.text
        assert r.json()["price_paise"] == 19900

    def test_price_change_not_retroactive(self, sp_store_token):
        fake_provider = FakeBillingProvider()
        original = _create_pending(sp_store_token, fake_provider)
        assert original["amount_paise"] == 19900

        r = client.post("/sponsored-posts/admin/price", json={"price_paise": 29900}, headers=ADMIN_HEADERS)
        assert r.status_code == 200, r.text
        assert r.json()["price_paise"] == 29900

        fresh = _create_pending(sp_store_token, fake_provider)
        assert fresh["amount_paise"] == 29900

        history = client.get("/stores/sponsored-posts", headers=_headers(sp_store_token))
        original_item = next(i for i in history.json()["items"] if i["id"] == original["sponsored_post_id"])
        assert original_item["amount_paise"] == 19900
