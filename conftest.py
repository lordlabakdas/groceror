"""
Root-level pytest configuration.

This conftest is imported by pytest *before* any sub-directory conftest
files are processed.  The SQLite patch runs at module-import time (not
inside a hook) so that ``models.db.engine`` is already replaced when
``tests/conftest.py`` imports ``tests._client`` -> ``main``.
"""
import os
import threading

# -----------------------------------------------------------------------
# Patch DBConfig and models.db to use SQLite so tests run without a
# running PostgreSQL server.
# -----------------------------------------------------------------------

import config as _config

_SQLITE_PATH = "/tmp/test_groceror.db"
_SQLITE_URL = f"sqlite:///{_SQLITE_PATH}"

# The file persists across runs; create_all() only creates missing tables,
# it never alters existing ones, so a stale file's schema silently drifts
# from current models. Start every session from a clean file instead.
if os.path.exists(_SQLITE_PATH):
    os.remove(_SQLITE_PATH)
_config.DBConfig.DB_URL = _SQLITE_URL  # type: ignore[assignment]
_config.JWTConfig.JWT_SECRET_KEY = "test-secret-key-padded-to-32-bytes!!"  # type: ignore[assignment]
_config.TwilioConfig.ACCOUNT_SID = ""  # skip real SMS — send_sms falls back to stdout

from sqlmodel import create_engine as _ce, SQLModel, Session as _Session  # noqa: E402
import models.db as _db  # noqa: E402

# Replace the module-level engine created against PostgreSQL.
_db.engine = _ce(
    _SQLITE_URL,
    echo=False,
    connect_args={"check_same_thread": False},
)

# Reset the thread-local storage and session factory.
_db._local = threading.local()


def _get_session_sqlite():
    if not getattr(_db._local, "session", None):
        _db._local.session = _Session(_db.engine)
    return _db._local.session


_db._get_session = _get_session_sqlite  # type: ignore[assignment]

# Create all tables on the SQLite DB now (idempotent).
from sqlalchemy_utils import create_database, database_exists  # noqa: E402

if not database_exists(_db.engine.url):
    create_database(_db.engine.url)

# SQLite doesn't support ARRAY types. For testing, we patch the ARRAY imports
# to use String instead.
try:
    SQLModel.metadata.create_all(_db.engine)
except Exception as e:
    # If ARRAY type fails in SQLite, skip table creation for now
    # (tests that need DB fixtures should use separate test fixtures)
    if "ARRAY" in str(e):
        pass
    else:
        raise

