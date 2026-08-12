"""Run the FastAPI app against an isolated SQLite DB, for Playwright e2e runs.

Mirrors the patching conftest.py does for pytest (see root conftest.py):
SQLite instead of the real Postgres, and Twilio disabled so OTPs land in
this process's stdout / are readable straight from the DB file rather than
sent as real SMS. Playwright's e2e tests read the OTP directly from
E2E_SQLITE_PATH (see groceror-fe/e2e/helpers/otp.ts) instead of a phone.

Never point this at the real DATABASE_URL — it always overrides to SQLite.
"""
import os
import sys
import threading

# Run by path (`python scripts/run_e2e_server.py`), so sys.path[0] is
# scripts/ rather than the project root — add the root so `import config`
# etc. resolve the same way they do for `main.py` / pytest.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_SQLITE_PATH = os.environ.get("E2E_SQLITE_PATH", "/tmp/test_groceror_e2e.db")
_SQLITE_URL = f"sqlite:///{_SQLITE_PATH}"

if os.path.exists(_SQLITE_PATH):
    os.remove(_SQLITE_PATH)

import config as _config  # noqa: E402

_config.DBConfig.DB_URL = _SQLITE_URL  # type: ignore[assignment]
_config.TwilioConfig.ACCOUNT_SID = ""  # skip real SMS — send_sms falls back to stdout

from sqlmodel import create_engine as _ce, SQLModel, Session as _Session  # noqa: E402
import models.db as _db  # noqa: E402

_db.engine = _ce(
    _SQLITE_URL,
    echo=False,
    connect_args={"check_same_thread": False},
)
_db._local = threading.local()


def _get_session_sqlite():
    if not getattr(_db._local, "session", None):
        _db._local.session = _Session(_db.engine)
    return _db._local.session


_db._get_session = _get_session_sqlite  # type: ignore[assignment]

SQLModel.metadata.create_all(_db.engine)

if __name__ == "__main__":
    import uvicorn
    from main import app

    port = int(os.environ.get("E2E_BACKEND_PORT", 8000))
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")
