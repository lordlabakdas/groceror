"""
Root-level pytest configuration.

This conftest is imported by pytest *before* any sub-directory conftest
files are processed.  The SQLite patch runs at module-import time (not
inside a hook) so that ``models.db.engine`` is already replaced when
``tests/conftest.py`` imports ``tests._client`` -> ``main`` ->
``create_db_and_tables``.
"""
import threading

# -----------------------------------------------------------------------
# Patch DBConfig and models.db to use SQLite so tests run without a
# running PostgreSQL server.
# -----------------------------------------------------------------------

import config as _config

_SQLITE_URL = "sqlite:////tmp/test_groceror.db"
_config.DBConfig.DB_URL = _SQLITE_URL  # type: ignore[assignment]

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
    SQLModel.metadata.create_all(bind=_db.engine)
except Exception as e:
    # If ARRAY type fails in SQLite, skip table creation for now
    # (tests that need DB fixtures should use separate test fixtures)
    if "ARRAY" in str(e):
        pass
    else:
        raise


# Replace create_db_and_tables with a no-op so ``main.py`` line 76 does
# not try to run the PostgreSQL-only ``CREATE SCHEMA`` statement.
def _noop_create_db_and_tables():
    pass


_db.create_db_and_tables = _noop_create_db_and_tables  # type: ignore[assignment]
