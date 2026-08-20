"""
Integration tests for subscription billing (SPEC_SUBSCRIPTION.md).

Uses FakeBillingProvider throughout — constitution Principle II forbids
live vendor calls in the test suite, and RazorpayProvider is explicitly
unverified against real docs anyway (see engine/billing/razorpay_provider.py).
"""

import uuid
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from sqlmodel import select

from config import AdminConfig
from engine.billing.fake_provider import VALID_SIGNATURE, FakeBillingProvider
from models.db import db_session
from models.entity.subscription_entity import Subscription
from models.entity.subscription_plan_entity import SubscriptionPlan
from tests.integration.helpers import _headers, _login, _otp_and_verify, _register, client

_suffix = str(uuid.uuid4().int)[:6]
ADMIN_HEADERS = {"x-admin-token": AdminConfig.ADMIN_TOKEN}


def _phone(n: str) -> str:
    return f"+1571{_suffix}{n}"


@pytest.fixture(scope="module", autouse=True)
def seeded_plan():
    """The real deploy seeds this via the Alembic migration (§ migration
    b3c4d5e6f7a8); the SQLite test DB only gets SQLModel.metadata.create_all,
    so tests need their own seed row."""
    plan = SubscriptionPlan(price_paise=99900, created_by="test-seed")
    db_session.add(plan)
    db_session.commit()
    return plan


def _create_store(n: str) -> tuple[str, str]:
    """Returns (store_token, store_id)."""
    _otp_and_verify(_phone(n))
    _register(_phone(n), "store")
    token = _login(_phone(n))
    r = client.post(
        "/stores/",
        json={
            "name": f"Billing Test Store {n}",
            "email": f"billingtest{n}@groceror.test",
            "website": f"https://billingtest{n}.groceror.test",
            "location": "1 Test Street",
        },
        headers=_headers(token),
    )
    assert r.status_code == 201, r.text
    return token, r.json()["id"]


class TestTrialOnSignup:
    def test_store_creation_starts_a_trial(self):
        token, store_id = _create_store("1")
        r = client.get("/subscription/status", headers=_headers(token))
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "trialing"
        assert body["checkout_needed"] is True
        assert body["plan_price_paise"] == 99900  # preview of the current plan, not snapshotted yet

    def test_mutation_endpoints_work_during_trial(self):
        token, store_id = _create_store("2")
        r = client.post(
            "/coupons",
            json={"code": f"TRIAL{_suffix}", "discount_type": "fixed", "discount_value": 5},
            headers=_headers(token),
        )
        assert r.status_code == 201, r.text


class TestCheckoutAndWebhook:
    def test_charged_webhook_activates_subscription_and_snapshots_price(self):
        token, store_id = _create_store("3")
        fake_provider = FakeBillingProvider()

        with patch("models.service.subscription_service.get_billing_provider", return_value=fake_provider):
            r = client.post("/subscription/checkout", headers=_headers(token))
            assert r.status_code == 200, r.text
            razorpay_subscription_id = r.json()["razorpay_subscription_id"]

        webhook_payload = {
            "event": "subscription.charged",
            "payload": {
                "subscription": {
                    "entity": {
                        "id": razorpay_subscription_id,
                        "current_start": int(datetime.utcnow().timestamp()),
                        "current_end": int((datetime.utcnow() + timedelta(days=30)).timestamp()),
                    }
                },
                "payment": {"entity": {"id": "fake_pay_1", "amount": 99900}},
            },
        }
        with patch("api.webhook_api.get_billing_provider", return_value=fake_provider):
            r = client.post(
                "/webhooks/razorpay-subscription",
                json=webhook_payload,
                headers={"X-Razorpay-Signature": VALID_SIGNATURE},
            )
            assert r.status_code == 200, r.text

        r = client.get("/subscription/status", headers=_headers(token))
        assert r.json()["status"] == "active"
        assert r.json()["plan_price_paise"] == 99900

    def test_webhook_rejected_without_valid_signature(self):
        fake_provider = FakeBillingProvider()
        with patch("api.webhook_api.get_billing_provider", return_value=fake_provider):
            r = client.post(
                "/webhooks/razorpay-subscription",
                json={"event": "subscription.charged", "payload": {"subscription": {"entity": {"id": "x"}}}},
                headers={"X-Razorpay-Signature": "not-the-real-signature"},
            )
            assert r.status_code == 401


class TestLockEnforcement:
    def test_locked_store_blocks_mutations_but_not_reads(self):
        token, store_id = _create_store("4")

        sub = db_session.exec(select(Subscription).where(Subscription.store_id == uuid.UUID(store_id))).first()
        sub.status = "grace"
        sub.grace_period_end = datetime.utcnow() - timedelta(days=1)  # already expired
        db_session.add(sub)
        db_session.commit()

        # Read endpoint stays open and, as a side effect of the lazy
        # recompute (§3.2), flips this store to locked.
        r = client.get("/subscription/status", headers=_headers(token))
        assert r.status_code == 200
        assert r.json()["status"] == "locked"

        # Mutation endpoint is now blocked.
        r = client.post(
            "/coupons",
            json={"code": f"LOCKED{_suffix}", "discount_type": "fixed", "discount_value": 5},
            headers=_headers(token),
        )
        assert r.status_code == 402

        # But the store's own order-facing read endpoint (a stand-in for
        # "can still fulfill orders already placed") stays open.
        r = client.get("/order/store-orders", headers=_headers(token))
        assert r.status_code == 200


class TestAdminPlanPrice:
    def test_price_change_is_not_retroactive(self):
        token_a, store_id_a = _create_store("5")
        fake_provider = FakeBillingProvider()
        with patch("models.service.subscription_service.get_billing_provider", return_value=fake_provider):
            r = client.post("/subscription/checkout", headers=_headers(token_a))
            assert r.status_code == 200, r.text

        r = client.get("/subscription/status", headers=_headers(token_a))
        assert r.json()["plan_price_paise"] == 99900

        r = client.post("/subscription/admin/plan-price", json={"price_paise": 149900}, headers=ADMIN_HEADERS)
        assert r.status_code == 200, r.text
        assert r.json()["price_paise"] == 149900

        # Store A already checked out — its snapshotted price is unchanged.
        r = client.get("/subscription/status", headers=_headers(token_a))
        assert r.json()["plan_price_paise"] == 99900

        # A brand-new store previews the new current price before checkout.
        token_b, store_id_b = _create_store("6")
        r = client.get("/subscription/status", headers=_headers(token_b))
        assert r.json()["plan_price_paise"] == 149900

    def test_admin_endpoints_require_token(self):
        # Missing X-Admin-Token: FastAPI's required Header(...) 422s before
        # _require_admin ever runs — same as the existing /store/{id}/verify.
        r = client.get("/subscription/admin/list")
        assert r.status_code == 422

        # Wrong token: _require_admin itself rejects with 403.
        r = client.get("/subscription/admin/list", headers={"x-admin-token": "wrong"})
        assert r.status_code == 403


class TestAdminUnlock:
    def test_unlock_restores_active_status(self):
        token, store_id = _create_store("7")
        sub = db_session.exec(select(Subscription).where(Subscription.store_id == uuid.UUID(store_id))).first()
        sub.status = "locked"
        db_session.add(sub)
        db_session.commit()

        r = client.post(f"/subscription/{store_id}/admin/unlock", headers=ADMIN_HEADERS)
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "active"

        r = client.post(
            "/coupons",
            json={"code": f"UNLOCKED{_suffix}", "discount_type": "fixed", "discount_value": 5},
            headers=_headers(token),
        )
        assert r.status_code == 201, r.text
