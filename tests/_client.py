"""
Single shared TestClient instance for all tests.

Importing TestClient(app) in multiple modules spawns multiple portal threads,
each holding its own SQLAlchemy session and connection.  A single shared
instance means all HTTP calls share one portal thread and one DB connection,
avoiding connection-pool exhaustion during long test runs.
"""
from fastapi.testclient import TestClient

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
