import threading

from sqlalchemy import text
from sqlalchemy_utils import create_database, database_exists
from sqlmodel import SQLModel, Session, create_engine

from config import DBConfig
# Import all SQLModel models so metadata is populated
from models.entity.phone_verification import PhoneVerification
from models.entity.user_entity import User
from models.entity.store_entity import Store

engine = create_engine(
    DBConfig.DB_URL, echo=True, connect_args={"options": "-c search_path=public"}
)

_local = threading.local()


def _get_session() -> Session:
    """Return the SQLModel Session for the current thread, creating one if needed."""
    if not getattr(_local, "session", None):
        _local.session = Session(engine)
    return _local.session


class _ThreadLocalSessionProxy:
    """Proxy that delegates all attribute access to the thread-local Session.

    This gives every thread its own Session while preserving the simple
    ``db_session.xxx()`` call convention used throughout the codebase.
    Call ``db_session.remove()`` at the end of a request to close and
    discard the thread-local session.
    """

    def __getattr__(self, name: str):
        if name == "remove":
            return self._remove
        return getattr(_get_session(), name)

    def _remove(self):
        session = getattr(_local, "session", None)
        if session is not None:
            session.close()
            _local.session = None


db_session = _ThreadLocalSessionProxy()


def create_db_and_tables():
    if not database_exists(engine.url):
        create_database(engine.url)

    with engine.begin() as conn:
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS public"))

    SQLModel.metadata.create_all(bind=engine)

    # Idempotent column additions for fields added after initial table creation.
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE store ADD COLUMN IF NOT EXISTS latitude FLOAT"))
        conn.execute(text("ALTER TABLE store ADD COLUMN IF NOT EXISTS longitude FLOAT"))
        conn.execute(text('ALTER TABLE "order" ADD COLUMN IF NOT EXISTS store_id UUID REFERENCES store(id)'))


def get_session():
    """FastAPI dependency that yields a per-request session."""
    session = _get_session()
    try:
        yield session
    finally:
        db_session.remove()
