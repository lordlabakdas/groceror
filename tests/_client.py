"""
Single shared TestClient instance for all tests.

Importing TestClient(app) in multiple modules spawns multiple portal threads,
each holding its own SQLAlchemy session and connection.  A single shared
instance means all HTTP calls share one portal thread and one DB connection,
avoiding connection-pool exhaustion during long test runs.
"""
from fastapi.testclient import TestClient

from main import app

client = TestClient(app)
