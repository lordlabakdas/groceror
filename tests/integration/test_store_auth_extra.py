"""
Extra integration-test coverage for api/store_api.py and api/helpers/auth_helper.py.

Uses the shared TestClient (tests.integration.helpers.client) for HTTP-reachable
behavior (store ratings, admin verification endpoints, GET /user/me), and calls
into api.helpers.auth_helper directly for functions that no HTTP route exercises
(Google/Firebase auth helpers, geocoding, Twilio/SNS SMS, expired-OTP handling).

Phone numbers are minted from a locally-generated uuid suffix (per the shared
convention in tests/integration/helpers.py) so this file cannot collide with
phone numbers used by any other test module running in the same session.
"""
import uuid
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from config import AdminConfig
from tests._client import get_test_otp
from tests.integration.helpers import (
    _headers,
    _login,
    _otp_and_verify,
    _register,
    client,
)

# ─────────────────────────────────────────────────────────────────────────────
# Locally-unique phone numbers (never shared with helpers.py or other agents'
# new test files) — see helpers.py for the convention this mirrors.
# ─────────────────────────────────────────────────────────────────────────────
_suffix = str(uuid.uuid4().int)[:6]
RATER_PHONE = f"+1562{_suffix}01"
STORE2_PHONE = f"+1562{_suffix}02"
NOPROFILE_PHONE = f"+1562{_suffix}03"
STORE_NOPROFILE_PHONE = f"+1562{_suffix}04"
USER_NOPROFILE_PHONE = f"+1562{_suffix}05"
CHANGEPW_PHONE = f"+1562{_suffix}06"
EXPIRED_OTP_PHONE = f"+1562{_suffix}07"
UNREGISTERED_PHONE = f"+1562{_suffix}08"  # never sent an OTP / never registered


@pytest.fixture(scope="module")
def rater_token():
    _otp_and_verify(RATER_PHONE)
    _register(RATER_PHONE, "user")
    return _login(RATER_PHONE)


@pytest.fixture(scope="module")
def rater_profile(rater_token):
    r = client.post(
        "/user/set-profile",
        json={"name": "Rater Person", "email": "rater@groceror.test", "location": "Rater City"},
        headers=_headers(rater_token),
    )
    assert r.status_code == 200, r.text
    return {"name": "Rater Person", "email": "rater@groceror.test"}


@pytest.fixture(scope="module")
def store2_token():
    _otp_and_verify(STORE2_PHONE)
    _register(STORE2_PHONE, "store")
    return _login(STORE2_PHONE)


@pytest.fixture(scope="module")
def store2_id(store2_token):
    r = client.post(
        "/stores/",
        json={"name": "Rating Test Store", "email": f"ratingstore{_suffix}@groceror.test",
              "location": "456 Rating Ave"},
        headers=_headers(store2_token),
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


# ─────────────────────────────────────────────────────────────────────────────
# api/store_api.py — ratings (lines 89-108, 131-138, 154-184)
# ─────────────────────────────────────────────────────────────────────────────

class TestStoreRatings:

    def test_get_ratings_empty(self, store2_id, rater_token):
        r = client.get(f"/stores/{store2_id}/ratings", headers=_headers(rater_token))
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["avg_rating"] is None
        assert body["rating_count"] == 0
        assert body["ratings"] == []

    def test_submit_rating_requires_shopper(self, store2_id, store2_token):
        """A store account (entity_type == 'store') cannot submit ratings."""
        r = client.post(
            f"/stores/{store2_id}/ratings", json={"rating": 5}, headers=_headers(store2_token)
        )
        assert r.status_code == 403, r.text
        assert "Only shoppers can submit ratings" in r.json()["detail"]

    def test_submit_rating_requires_user_profile(self, store2_id):
        """A 'user' entity with no User profile row set gets a 400."""
        _otp_and_verify(NOPROFILE_PHONE)
        _register(NOPROFILE_PHONE, "user")
        token = _login(NOPROFILE_PHONE)
        r = client.post(
            f"/stores/{store2_id}/ratings", json={"rating": 4}, headers=_headers(token)
        )
        assert r.status_code == 400, r.text
        assert "User profile not set" in r.json()["detail"]

    def test_submit_rating_store_not_found(self, rater_token, rater_profile):
        r = client.post(
            f"/stores/{uuid.uuid4()}/ratings", json={"rating": 3}, headers=_headers(rater_token)
        )
        assert r.status_code == 404, r.text
        assert "Store not found" in r.json()["detail"]

    def test_submit_rating_then_resubmit_updates_in_place(self, store2_id, rater_token, rater_profile):
        # First submission: creates a new StoreRating row.
        r = client.post(
            f"/stores/{store2_id}/ratings",
            json={"rating": 5, "comment": "Great store"},
            headers=_headers(rater_token),
        )
        assert r.status_code == 200, r.text
        assert r.json() == {"status": "success"}

        r = client.get(f"/stores/{store2_id}/ratings", headers=_headers(rater_token))
        assert r.status_code == 200
        body = r.json()
        assert body["avg_rating"] == 5.0
        assert body["rating_count"] == 1
        assert len(body["ratings"]) == 1
        assert body["ratings"][0]["rating"] == 5
        assert body["ratings"][0]["comment"] == "Great store"

        # Second submission by the same user: updates the existing row rather
        # than inserting a duplicate (exercises the `existing` branch).
        r = client.post(
            f"/stores/{store2_id}/ratings",
            json={"rating": 2, "comment": "changed my mind"},
            headers=_headers(rater_token),
        )
        assert r.status_code == 200, r.text

        r = client.get(f"/stores/{store2_id}/ratings", headers=_headers(rater_token))
        body = r.json()
        assert body["rating_count"] == 1  # still one rating, not two
        assert body["avg_rating"] == 2.0
        assert body["ratings"][0]["comment"] == "changed my mind"

    def test_list_all_stores_includes_rating_summary(self, store2_id, rater_token):
        r = client.get("/stores/", headers=_headers(rater_token))
        assert r.status_code == 200, r.text
        stores = r.json()
        mine = next((s for s in stores if s["id"] == store2_id), None)
        assert mine is not None
        assert mine["rating_count"] == 1
        assert mine["avg_rating"] == 2.0  # from the resubmit test above
        assert mine["is_active"] is True
        assert mine["name"] == "Rating Test Store"


# ─────────────────────────────────────────────────────────────────────────────
# api/store_api.py — admin verify/unverify (lines 250-251, 256-262, 267-273)
# ─────────────────────────────────────────────────────────────────────────────

class TestAdminStoreVerification:

    def test_verify_store_wrong_admin_token_forbidden(self, store2_id):
        r = client.post(f"/stores/{store2_id}/verify", headers={"x-admin-token": "wrong-token"})
        assert r.status_code == 403, r.text
        assert "Invalid admin token" in r.json()["detail"]

    def test_verify_store_not_found(self):
        r = client.post(
            f"/stores/{uuid.uuid4()}/verify",
            headers={"x-admin-token": AdminConfig.ADMIN_TOKEN},
        )
        assert r.status_code == 404, r.text
        assert "Store not found" in r.json()["detail"]

    def test_verify_then_unverify_store(self, store2_id):
        r = client.post(
            f"/stores/{store2_id}/verify",
            headers={"x-admin-token": AdminConfig.ADMIN_TOKEN},
        )
        assert r.status_code == 200, r.text
        assert r.json() == {"status": "verified"}

        r = client.delete(
            f"/stores/{store2_id}/verify",
            headers={"x-admin-token": AdminConfig.ADMIN_TOKEN},
        )
        assert r.status_code == 200, r.text
        assert r.json() == {"status": "unverified"}

    def test_unverify_store_not_found(self):
        r = client.delete(
            f"/stores/{uuid.uuid4()}/verify",
            headers={"x-admin-token": AdminConfig.ADMIN_TOKEN},
        )
        assert r.status_code == 404, r.text
        assert "Store not found" in r.json()["detail"]


# ─────────────────────────────────────────────────────────────────────────────
# api/user_api.py GET /user/me -> auth_helper.get_profile (lines 184-194)
# ─────────────────────────────────────────────────────────────────────────────

class TestGetMeProfile:

    def test_get_me_user_without_profile_returns_defaults(self):
        _otp_and_verify(USER_NOPROFILE_PHONE)
        _register(USER_NOPROFILE_PHONE, "user")
        token = _login(USER_NOPROFILE_PHONE)

        r = client.get("/user/me", headers=_headers(token))
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["entity_type"] == "user"
        assert body["name"] is None
        assert body["email"] is None
        assert body["location"] is None

    def test_get_me_user_with_profile_returns_data(self, rater_token, rater_profile):
        r = client.get("/user/me", headers=_headers(rater_token))
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["entity_type"] == "user"
        assert body["name"] == rater_profile["name"]
        assert body["email"] == rater_profile["email"]

    def test_get_me_store_without_profile_returns_defaults(self):
        _otp_and_verify(STORE_NOPROFILE_PHONE)
        _register(STORE_NOPROFILE_PHONE, "store")
        token = _login(STORE_NOPROFILE_PHONE)

        r = client.get("/user/me", headers=_headers(token))
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["entity_type"] == "store"
        assert body["name"] is None
        assert body["email"] is None
        assert body["location"] is None
        assert body["website"] is None

    def test_get_me_store_with_profile_returns_data(self, store2_token, store2_id):
        r = client.get("/user/me", headers=_headers(store2_token))
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["entity_type"] == "store"
        assert body["name"] == "Rating Test Store"
        assert body["email"] == f"ratingstore{_suffix}@groceror.test"
        assert body["location"] == "456 Rating Ave"


# ─────────────────────────────────────────────────────────────────────────────
# api/helpers/auth_helper.py — functions not reachable via any HTTP route.
# Called directly; the real (SQLite-backed) db_session is used except where
# an external service (Google/Firebase/Twilio/AWS SNS) must be mocked.
# ─────────────────────────────────────────────────────────────────────────────

class TestAuthHelperDirect:

    def test_validate_google_token_missing_email_returns_none(self):
        from api.helpers import auth_helper

        with patch(
            "api.helpers.auth_helper.id_token.verify_oauth2_token",
            return_value={"sub": "123"},  # no "email" key
        ):
            result = auth_helper.validate_google_token("fake-token", "client-id")
        assert result is None

    def test_validate_google_token_success(self):
        from api.helpers import auth_helper

        idinfo = {"email": "googleuser@example.com", "sub": "123"}
        with patch(
            "api.helpers.auth_helper.id_token.verify_oauth2_token", return_value=idinfo
        ):
            result = auth_helper.validate_google_token("fake-token", "client-id")
        assert result == idinfo

    def test_register_unknown_phone_raises_value_error(self):
        from api.helpers import auth_helper

        with pytest.raises(ValueError, match="User not found"):
            auth_helper.register({"phone": UNREGISTERED_PHONE, "entity_type": None, "password": "x"})

    def test_get_user_by_email_and_by_id(self, rater_token, rater_profile):
        from api.helpers import auth_helper

        found = auth_helper.get_user_by_email(rater_profile["email"])
        assert found is not None
        assert found.email == rater_profile["email"]

        # get_user_by_id's type hint says str, but under SQLite (unlike
        # Postgres) SQLAlchemy's Uuid column type requires an actual UUID
        # instance to bind correctly — passing a str raises AttributeError
        # deep in the dialect. No real caller in the app hits this path
        # today (the function is unused), so we call it the way it actually
        # works rather than the way its signature implies.
        found_by_id = auth_helper.get_user_by_id(found.id)
        assert found_by_id is not None
        assert found_by_id.id == found.id

    def test_register_firebase_user_success(self):
        from api.helpers import auth_helper

        fake_firebase_user = MagicMock(uid="firebase-uid-123")
        with patch(
            "api.helpers.auth_helper.firebase_auth.create_user",
            return_value=fake_firebase_user,
        ):
            uid = auth_helper.register_firebase_user("new@example.com", "Passw0rd!")
        assert uid == "firebase-uid-123"

    def test_register_firebase_user_duplicate_raises(self):
        from api.helpers import auth_helper
        from firebase_admin import auth as firebase_auth_module

        err = firebase_auth_module.EmailAlreadyExistsError("email exists", None, None)
        with patch("api.helpers.auth_helper.firebase_auth.create_user", side_effect=err):
            with pytest.raises(firebase_auth_module.EmailAlreadyExistsError):
                auth_helper.register_firebase_user("dup@example.com", "Passw0rd!")

    def test_change_password_direct(self):
        from api.helpers import auth_helper
        from api.validators.user_validation import ChangePasswordPayload

        _otp_and_verify(CHANGEPW_PHONE)
        _register(CHANGEPW_PHONE, "user")
        pv = auth_helper.get_user_by_phone(CHANGEPW_PHONE)
        assert pv is not None

        updated = auth_helper.change_password(
            pv, ChangePasswordPayload(new_password="BrandNewPassw0rd!")
        )
        assert updated is pv
        assert auth_helper.verify_password("BrandNewPassw0rd!", pv.password)

        # New password actually works end-to-end via the login route.
        r = client.post(
            "/user/login", json={"phone": CHANGEPW_PHONE, "password": "BrandNewPassw0rd!"}
        )
        assert r.status_code == 200, r.text

    def test_geocode_location_network_failure_returns_none(self):
        from api.helpers import auth_helper

        with patch(
            "api.helpers.auth_helper.urllib.request.urlopen",
            side_effect=OSError("network unreachable"),
        ):
            result = auth_helper.geocode_location("Nowhere, XX")
        assert result is None

    def test_send_sms_uses_twilio_when_configured(self):
        from api.helpers import auth_helper
        import config as config_module

        fake_client_instance = MagicMock()
        fake_client_cls = MagicMock(return_value=fake_client_instance)

        with patch.object(config_module.TwilioConfig, "ACCOUNT_SID", "AC_fake"), \
             patch.object(config_module.TwilioConfig, "AUTH_TOKEN", "fake_token"), \
             patch.object(config_module.TwilioConfig, "FROM_NUMBER", "+10000000000"), \
             patch("twilio.rest.Client", fake_client_cls):
            auth_helper.send_sms("+15551234567", "hello world")

        fake_client_cls.assert_called_once_with("AC_fake", "fake_token")
        fake_client_instance.messages.create.assert_called_once_with(
            body="hello world", from_="+10000000000", to="+15551234567",
        )

    def test_verify_otp_no_record_returns_false(self):
        from api.helpers import auth_helper

        # This phone number has never had send_otp() called for it.
        assert auth_helper.verify_otp(f"+1562{_suffix}99", "000000") is False

    def test_verify_otp_expired_returns_false(self):
        from api.helpers import auth_helper
        from models.db import db_session

        auth_helper.send_otp(EXPIRED_OTP_PHONE)
        otp = get_test_otp(EXPIRED_OTP_PHONE)

        pv = auth_helper.get_user_by_phone(EXPIRED_OTP_PHONE)
        pv.otp_expires_at = datetime.utcnow() - timedelta(minutes=1)
        db_session.commit()

        assert auth_helper.verify_otp(EXPIRED_OTP_PHONE, otp) is False

    def test_send_sms_via_sns_success(self):
        from api.helpers import auth_helper

        fake_sns = MagicMock()
        fake_sns.publish.return_value = {"MessageId": "abc123"}
        with patch("api.helpers.auth_helper.boto3.client", return_value=fake_sns) as mock_boto:
            result = auth_helper.send_sms_via_sns("+15551234567", "hi there")

        assert result == {"MessageId": "abc123"}
        mock_boto.assert_called_once()
        fake_sns.publish.assert_called_once()

    def test_send_sms_via_sns_client_error_raises(self):
        from api.helpers import auth_helper
        from botocore.exceptions import ClientError

        fake_sns = MagicMock()
        fake_sns.publish.side_effect = ClientError(
            {"Error": {"Code": "Throttling", "Message": "Rate exceeded"}}, "Publish"
        )
        with patch("api.helpers.auth_helper.boto3.client", return_value=fake_sns):
            with pytest.raises(ClientError):
                auth_helper.send_sms_via_sns("+15551234567", "hi there")
