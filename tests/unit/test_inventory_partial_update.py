"""
Tests for partial inventory update:
- UpdateInventoryPayload accepts quantity-only or price-only
- update_inventory_fields only writes provided fields
"""
from unittest.mock import MagicMock, patch
from uuid import uuid4


# ---------------------------------------------------------------------------
# Validator tests — no DB needed
# ---------------------------------------------------------------------------

def test_payload_price_only():
    from api.validators.inventory_validation import UpdateInventoryPayload
    p = UpdateInventoryPayload(price=3.99)
    assert p.price == 3.99
    assert p.quantity is None


def test_payload_quantity_only():
    from api.validators.inventory_validation import UpdateInventoryPayload
    p = UpdateInventoryPayload(quantity=10)
    assert p.quantity == 10
    assert p.price is None


def test_payload_both_fields():
    from api.validators.inventory_validation import UpdateInventoryPayload
    p = UpdateInventoryPayload(quantity=5, price=2.99)
    assert p.quantity == 5
    assert p.price == 2.99


def test_payload_empty_is_valid():
    from api.validators.inventory_validation import UpdateInventoryPayload
    p = UpdateInventoryPayload()
    assert p.quantity is None
    assert p.price is None


def test_update_with_no_fields_is_noop():
    """Passing neither quantity nor price updates only updated_at — no field mutation."""
    item_id = uuid4()
    mock_store = MagicMock()
    mock_store.id = uuid4()

    mock_item = MagicMock()
    mock_item.quantity = 7
    mock_item.price = 1.50

    with patch("api.helpers.inventory_helper.db_session") as mock_db:
        mock_exec_store = MagicMock()
        mock_exec_store.first.return_value = mock_store
        mock_exec_item = MagicMock()
        mock_exec_item.first.return_value = mock_item
        mock_db.exec.side_effect = [mock_exec_store, mock_exec_item]

        from api.helpers.inventory_helper import InventoryHelper
        helper = InventoryHelper(user=MagicMock())
        helper.update_inventory_fields(item_id)  # no quantity, no price

    assert mock_item.quantity == 7   # unchanged
    assert mock_item.price == 1.50  # unchanged
    mock_db.commit.assert_called_once()


# ---------------------------------------------------------------------------
# Helper tests — db_session mocked
# ---------------------------------------------------------------------------

def test_update_price_only_leaves_quantity_unchanged():
    item_id = uuid4()
    mock_store = MagicMock()
    mock_store.id = uuid4()

    mock_item = MagicMock()
    mock_item.quantity = 10
    mock_item.price = 1.99

    with patch("api.helpers.inventory_helper.db_session") as mock_db:
        mock_exec_store = MagicMock()
        mock_exec_store.first.return_value = mock_store
        mock_exec_item = MagicMock()
        mock_exec_item.first.return_value = mock_item
        mock_db.exec.side_effect = [mock_exec_store, mock_exec_item]

        from api.helpers.inventory_helper import InventoryHelper
        helper = InventoryHelper(user=MagicMock())
        helper.update_inventory_fields(item_id, price=4.50)

    assert mock_item.price == 4.50
    assert mock_item.quantity == 10  # unchanged


def test_update_quantity_only_leaves_price_unchanged():
    item_id = uuid4()
    mock_store = MagicMock()
    mock_store.id = uuid4()

    mock_item = MagicMock()
    mock_item.quantity = 5
    mock_item.price = 2.99

    with patch("api.helpers.inventory_helper.db_session") as mock_db:
        mock_exec_store = MagicMock()
        mock_exec_store.first.return_value = mock_store
        mock_exec_item = MagicMock()
        mock_exec_item.first.return_value = mock_item
        mock_db.exec.side_effect = [mock_exec_store, mock_exec_item]

        from api.helpers.inventory_helper import InventoryHelper
        helper = InventoryHelper(user=MagicMock())
        helper.update_inventory_fields(item_id, quantity=20)

    assert mock_item.quantity == 20
    assert mock_item.price == 2.99  # unchanged


def test_update_missing_item_raises():
    item_id = uuid4()
    mock_store = MagicMock()
    mock_store.id = uuid4()

    with patch("api.helpers.inventory_helper.db_session") as mock_db:
        mock_exec_store = MagicMock()
        mock_exec_store.first.return_value = mock_store
        mock_exec_item = MagicMock()
        mock_exec_item.first.return_value = None
        mock_db.exec.side_effect = [mock_exec_store, mock_exec_item]

        from api.helpers.inventory_helper import InventoryHelper
        helper = InventoryHelper(user=MagicMock())

        try:
            helper.update_inventory_fields(item_id, price=1.99)
            assert False, "Expected ValueError"
        except ValueError as e:
            assert "not found" in str(e).lower()
