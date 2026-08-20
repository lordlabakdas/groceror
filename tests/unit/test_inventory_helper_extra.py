"""
Unit tests (mocked db_session) for InventoryHelper code paths that have no
HTTP route calling them — get_inventory_by_category, get_inventory_by_name,
and the whole-object update_inventory() (distinct from update_inventory_fields,
which IS reachable via PUT /inventory/{id} and is covered both in
tests/unit/test_inventory_partial_update.py and in
tests/integration/test_inventory_dashboard.py).

Also covers the 500 branch of PUT /inventory/{id} (api/inventory_api.py
update_inventory), which requires forcing InventoryHelper to raise a plain
Exception — not reachable through real HTTP + SQLite without mocking.
"""
from unittest.mock import MagicMock, patch
from uuid import uuid4

from models.entity.inventory_entity import Inventory, InventoryCategory


# ---------------------------------------------------------------------------
# _require_store
# ---------------------------------------------------------------------------

def test_require_store_raises_when_no_store():
    with patch("api.helpers.inventory_helper.db_session") as mock_db:
        exec_store = MagicMock()
        exec_store.first.return_value = None
        mock_db.exec.return_value = exec_store

        from api.helpers.inventory_helper import InventoryHelper
        helper = InventoryHelper(user=MagicMock())

        try:
            helper._require_store()
            assert False, "expected ValueError"
        except ValueError as e:
            assert "No store found" in str(e)


# ---------------------------------------------------------------------------
# get_inventory_by_category
# ---------------------------------------------------------------------------

def test_get_inventory_by_category_returns_dicts():
    store = MagicMock()
    store.id = uuid4()

    item = MagicMock()
    item.to_dict.return_value = {"name": "Milk", "category": "DAIRY"}

    with patch("api.helpers.inventory_helper.db_session") as mock_db:
        exec_store = MagicMock()
        exec_store.first.return_value = store
        exec_items = MagicMock()
        exec_items.all.return_value = [item]
        mock_db.exec.side_effect = [exec_store, exec_items]

        from api.helpers.inventory_helper import InventoryHelper
        helper = InventoryHelper(user=MagicMock())
        result = helper.get_inventory_by_category(InventoryCategory.DAIRY)

    assert result == [{"name": "Milk", "category": "DAIRY"}]
    item.to_dict.assert_called_once()


def test_get_inventory_by_category_no_store_raises():
    with patch("api.helpers.inventory_helper.db_session") as mock_db:
        exec_store = MagicMock()
        exec_store.first.return_value = None
        mock_db.exec.return_value = exec_store

        from api.helpers.inventory_helper import InventoryHelper
        helper = InventoryHelper(user=MagicMock())

        try:
            helper.get_inventory_by_category(InventoryCategory.DAIRY)
            assert False, "expected ValueError"
        except ValueError:
            pass


# ---------------------------------------------------------------------------
# get_inventory_by_name
# ---------------------------------------------------------------------------

def test_get_inventory_by_name_returns_dicts():
    store = MagicMock()
    store.id = uuid4()

    item = MagicMock()
    item.to_dict.return_value = {"name": "Bread"}

    with patch("api.helpers.inventory_helper.db_session") as mock_db:
        exec_store = MagicMock()
        exec_store.first.return_value = store
        exec_items = MagicMock()
        exec_items.all.return_value = [item]
        mock_db.exec.side_effect = [exec_store, exec_items]

        from api.helpers.inventory_helper import InventoryHelper
        helper = InventoryHelper(user=MagicMock())
        result = helper.get_inventory_by_name("Bread")

    assert result == [{"name": "Bread"}]


def test_get_inventory_by_name_empty_when_no_match():
    store = MagicMock()
    store.id = uuid4()

    with patch("api.helpers.inventory_helper.db_session") as mock_db:
        exec_store = MagicMock()
        exec_store.first.return_value = store
        exec_items = MagicMock()
        exec_items.all.return_value = []
        mock_db.exec.side_effect = [exec_store, exec_items]

        from api.helpers.inventory_helper import InventoryHelper
        helper = InventoryHelper(user=MagicMock())
        result = helper.get_inventory_by_name("Nonexistent")

    assert result == []


# ---------------------------------------------------------------------------
# update_inventory (whole-object variant — dead from an HTTP standpoint)
# ---------------------------------------------------------------------------

def test_update_inventory_whole_object_success():
    store = MagicMock()
    store.id = uuid4()

    existing = MagicMock()
    existing.quantity = 1
    existing.price = 1.0

    new_data = Inventory(
        id=uuid4(), name="Eggs", quantity=12, category=InventoryCategory.DAIRY,
        store_id=store.id, price=3.99,
    )

    with patch("api.helpers.inventory_helper.db_session") as mock_db:
        exec_store = MagicMock()
        exec_store.first.return_value = store
        exec_item = MagicMock()
        exec_item.first.return_value = existing
        mock_db.exec.side_effect = [exec_store, exec_item]

        from api.helpers.inventory_helper import InventoryHelper
        helper = InventoryHelper(user=MagicMock())
        helper.update_inventory(new_data)

    assert existing.quantity == 12
    assert existing.price == 3.99
    mock_db.commit.assert_called_once()


def test_update_inventory_whole_object_not_found_raises():
    store = MagicMock()
    store.id = uuid4()

    missing_data = Inventory(
        id=uuid4(), name="Eggs", quantity=12, category=InventoryCategory.DAIRY,
        store_id=store.id, price=3.99,
    )

    with patch("api.helpers.inventory_helper.db_session") as mock_db:
        exec_store = MagicMock()
        exec_store.first.return_value = store
        exec_item = MagicMock()
        exec_item.first.return_value = None
        mock_db.exec.side_effect = [exec_store, exec_item]

        from api.helpers.inventory_helper import InventoryHelper
        helper = InventoryHelper(user=MagicMock())

        try:
            helper.update_inventory(missing_data)
            assert False, "expected ValueError"
        except ValueError as e:
            assert "not found" in str(e).lower()


# ---------------------------------------------------------------------------
# PUT /inventory/{id} — 500 branch (generic exception from the helper)
# ---------------------------------------------------------------------------

def test_update_inventory_endpoint_returns_500_on_unexpected_error():
    from fastapi.testclient import TestClient
    from main import app
    from helpers.jwt import auth_required

    # A real UUID, not a bare MagicMock: update_inventory now runs through
    # _require_billing_ok first (SPEC_SUBSCRIPTION.md §3.3), which queries
    # Store.entity_id == user.id — a MagicMock() id isn't a bindable SQL
    # parameter. No Store matches this id, so the billing check is a no-op
    # and this test still exercises what it's actually testing: the mocked
    # InventoryHelper raising and the endpoint's generic 500 handling.
    mock_user = MagicMock(id=uuid4())

    async def override_auth():
        return mock_user

    app.dependency_overrides[auth_required] = override_auth
    try:
        with patch("api.inventory_api.InventoryHelper") as MockHelper:
            MockHelper.return_value.update_inventory_fields.side_effect = RuntimeError("boom")
            c = TestClient(app)
            r = c.put(f"/inventory/{uuid4()}", json={"quantity": 1})
            assert r.status_code == 500
            assert "Issue updating inventory" in r.json()["detail"]
    finally:
        app.dependency_overrides.pop(auth_required, None)
