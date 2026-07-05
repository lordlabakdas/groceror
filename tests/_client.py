"""
Single shared TestClient instance for all tests.

Importing TestClient(app) in multiple modules spawns multiple portal threads,
each holding its own SQLAlchemy session and connection.  A single shared
instance means all HTTP calls share one portal thread and one DB connection,
avoiding connection-pool exhaustion during long test runs.
"""
from fastapi.testclient import TestClient
from sqlmodel import select

from main import app


class _LazyTestClient:
    """Defers TestClient(app) creation until first attribute access.

    Avoids starlette/httpx version conflicts at module import time;
    the real client is only constructed when a test method is first called.
    """

    _instance: "TestClient | None" = None

    def _get(self) -> TestClient:
        if type(self)._instance is None:
            type(self)._instance = TestClient(app)
        return type(self)._instance

    def __getattr__(self, name: str):
        return getattr(self._get(), name)

    def __enter__(self):
        return self._get().__enter__()

    def __exit__(self, *args):
        return self._get().__exit__(*args)


client: TestClient = _LazyTestClient()  # type: ignore[assignment]


def get_test_otp(phone: str) -> str:
    """Read the OTP stored in the test DB for *phone*.

    The /user/otp API endpoint was removed (security: it returned OTPs over
    HTTP).  Tests that need the OTP for the registration flow use this helper
    instead — it only works because the tests have direct DB access.
    """
    from models.db import db_session
    from models.entity.phone_verification import PhoneVerification

    pv = db_session.exec(
        select(PhoneVerification).where(PhoneVerification.phone == phone)
    ).first()
    if pv is None or pv.otp is None:
        raise ValueError(f"No OTP found for phone {phone!r}")
    return pv.otp
