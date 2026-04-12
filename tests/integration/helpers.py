"""
Shared test helpers for integration tests.

Provides the shared TestClient instance (imported from tests._client to ensure
there is only one portal thread across all test files), phone-number constants
that are unique per test-module run (to avoid DB collisions on re-runs), and
the small HTTP helper functions used by both fixtures and test methods.
"""
import uuid

from tests._client import client  # noqa: F401  re-exported for convenience

# ─────────────────────────────────────────────────────────────────────────────
# Per-run unique phone suffixes (avoids DB collisions between test runs)
# ─────────────────────────────────────────────────────────────────────────────
_suffix = str(uuid.uuid4().int)[:6]
USER_PHONE  = f"+1555{_suffix}01"
STORE_PHONE = f"+1555{_suffix}02"
OTHER_PHONE = f"+1555{_suffix}03"   # second store owner (for 403 tests)
PASSWORD    = "grocerorTest1!"


# ─────────────────────────────────────────────────────────────────────────────
# HTTP helpers
# ─────────────────────────────────────────────────────────────────────────────

def _otp_and_verify(phone: str) -> None:
    """Send OTP via legacy endpoint (returns OTP directly) and verify it."""
    r = client.post("/user/otp", params={"phone": phone})
    assert r.status_code == 200, r.text
    otp = r.json()["otp"]
    r = client.post("/user/verify-otp", json={"phone": phone, "otp": otp})
    assert r.status_code == 200, r.text


def _register(phone: str, entity_type: str) -> None:
    r = client.post(
        "/user/register",
        json={"phone": phone, "entity_type": entity_type, "password": PASSWORD},
    )
    assert r.status_code == 200, r.text


def _login(phone: str) -> str:
    r = client.post("/user/login", json={"phone": phone, "password": PASSWORD})
    assert r.status_code == 200, r.text
    return r.json()["token"]


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}
