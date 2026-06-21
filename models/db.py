import threading

from sqlmodel import Session, create_engine

from config import DBConfig
# Import all SQLModel models so metadata is populated
from models.entity.phone_verification import PhoneVerification  # noqa: F401
from models.entity.user_entity import User  # noqa: F401
from models.entity.store_entity import Store  # noqa: F401
from models.entity.inventory_entity import Inventory  # noqa: F401
from models.entity.orders_entity import Order  # noqa: F401
from models.entity.stock_threshold_entity import StockThreshold  # noqa: F401
from models.entity.inventory_expiry_entity import InventoryExpiry  # noqa: F401
from models.entity.order_item_entity import OrderItem  # noqa: F401

engine = create_engine(
    DBConfig.DB_URL, echo=True, connect_args={"options": "-c search_path=public"}, pool_pre_ping=True
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


def get_session():
    """FastAPI dependency that yields a per-request session."""
    session = _get_session()
    try:
        yield session
    finally:
        db_session.remove()
