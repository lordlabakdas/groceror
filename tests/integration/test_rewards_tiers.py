"""
Integration coverage for the rewards-tiers feature (see SPEC_REWARDS_PROGRAM.md):
tier-scaled points earning on checkout, and tier/progress fields on
GET /loyalty/balance.

All accounts used here are created fresh with unique phone numbers so this
file has no shared mutable state with other test modules.
"""

import uuid
from unittest.mock import patch

import pytest

from tests.integration.helpers import (
    _headers,
    _login,
    _otp_and_verify,
    _register,
    client,
)

_suffix = str(uuid.uuid4().int)[:6]


def _phone(n: str) -> str:
    return f"+1570{_suffix}{n}"


@pytest.fixture(scope="module")
def rt_user_token():
    phone = _phone("01")
    _otp_and_verify(phone)
    _register(phone, "user")
    return _login(phone)


@pytest.fixture(scope="module")
def rt_user_profile(rt_user_token):
    r = client.post(
        "/user/set-profile",
        json={"name": "Rewards Tester", "email": "rewardstester@groceror.test"},
        headers=_headers(rt_user_token),
    )
    assert r.status_code == 200, r.text


@pytest.fixture(scope="module")
def rt_store_token():
    phone = _phone("02")
    _otp_and_verify(phone)
    _register(phone, "store")
    return _login(phone)


@pytest.fixture(scope="module")
def rt_store_profile(rt_store_token):
    r = client.post(
        "/user/set-profile",
        json={
            "name": "Tier Grocer",
            "email": "tiergrocer@groceror.test",
            "location": "1 Tier Ave",
        },
        headers=_headers(rt_store_token),
    )
    assert r.status_code == 200, r.text


@pytest.fixture(scope="module")
def rt_inventory_id(rt_store_token, rt_store_profile):
    r = client.post(
        "/inventory/add-inventory",
        json={
            "name": "Premium Basket",
            "quantity": 50,
            "category": "GROCERY",
            "price": 100.0,
        },
        headers=_headers(rt_store_token),
    )
    assert r.status_code == 200, r.text
    return r.json()["inventory_id"]


class TestRewardsTiers:

    def test_first_order_earns_at_bronze_rate_then_balance_shows_silver(
        self, rt_user_token, rt_user_profile, rt_inventory_id
    ):
        # Prior lifetime spend is $0 (bronze, 1.0x) — even though this $300
        # order itself crosses the $250 silver threshold, the multiplier
        # applied to IT is based on spend before it, not after.
        with patch("engine.mailer.Mailer.send"):
            r = client.post(
                "/order/create-order",
                json={
                    "items": [{"inventory_id": rt_inventory_id, "quantity": 3}]
                },  # $300
                headers=_headers(rt_user_token),
            )
        assert r.status_code == 200, r.text
        assert r.json()["points_earned"] == 300  # 300 * 1 * 1.0

        # Now that lifetime spend is $300, the balance endpoint should report
        # the shopper has already crossed into silver.
        bal = client.get("/loyalty/balance", headers=_headers(rt_user_token))
        assert bal.status_code == 200, bal.text
        data = bal.json()
        assert data["tier"] == "silver"
        assert data["multiplier"] == 1.25
        assert data["next_tier"] == "gold"
        assert data["spend_to_next_tier"] == 450.0  # 750 - 300

    def test_second_order_earns_at_silver_rate_then_balance_shows_gold(
        self, rt_user_token, rt_inventory_id
    ):
        # Prior lifetime spend is $300 (silver, 1.25x). This $500 order pushes
        # cumulative spend to $800 (gold), but earns at the silver rate.
        with patch("engine.mailer.Mailer.send"):
            r = client.post(
                "/order/create-order",
                json={
                    "items": [{"inventory_id": rt_inventory_id, "quantity": 5}]
                },  # $500
                headers=_headers(rt_user_token),
            )
        assert r.status_code == 200, r.text
        assert r.json()["points_earned"] == 625  # 500 * 1 * 1.25

        bal = client.get("/loyalty/balance", headers=_headers(rt_user_token))
        assert bal.status_code == 200, bal.text
        data = bal.json()
        assert data["tier"] == "gold"
        assert data["multiplier"] == 1.5
        assert data["next_tier"] is None
        assert data["spend_to_next_tier"] is None

    def test_balance_for_brand_new_user_is_bronze(self):
        phone = _phone("03")
        _otp_and_verify(phone)
        _register(phone, "user")
        token = _login(phone)
        client.post(
            "/user/set-profile",
            json={"name": "New Shopper", "email": "newshopper@groceror.test"},
            headers=_headers(token),
        )

        bal = client.get("/loyalty/balance", headers=_headers(token))
        assert bal.status_code == 200, bal.text
        data = bal.json()
        assert data["tier"] == "bronze"
        assert data["multiplier"] == 1.0
        assert data["next_tier"] == "silver"
        assert data["spend_to_next_tier"] == 250.0
