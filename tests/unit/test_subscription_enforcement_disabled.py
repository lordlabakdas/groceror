"""Subscription state must not restrict store operations or discovery."""
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import pytest
from sqlmodel import Session, SQLModel, create_engine

from models.entity.store_entity import Store
from models.service import subscription_service as subscriptions
from models.service.store_service import StoreService


def test_enforcement_is_disabled_by_default():
    assert subscriptions.SUBSCRIPTION_ENFORCEMENT_ENABLED is False


def test_store_mutations_do_not_read_or_enforce_subscription():
    with patch.object(subscriptions, "get_status_for_store", side_effect=AssertionError("billing lookup")):
        subscriptions.assert_billing_ok(SimpleNamespace(id=uuid4(), is_billing_locked=True))


@pytest.mark.parametrize("state", ["trialing", "grace", "locked"])
def test_status_read_does_not_expire_subscription_and_clears_lock(state):
    sub = SimpleNamespace(store_id=uuid4(), status=state,
                          trial_end=datetime.utcnow() - timedelta(days=30),
                          grace_period_end=datetime.utcnow() - timedelta(days=1),
                          razorpay_subscription_id=None)
    with patch.object(subscriptions, "_sync_store_lock") as sync:
        assert subscriptions._recompute_status(sub) is sub
        assert sub.status == state
        sync.assert_called_once_with(sub.store_id, locked=False)


def test_no_deadline_email_is_sent():
    with patch.object(subscriptions, "db_session") as db:
        subscriptions._send_grace_email(SimpleNamespace(store_id=uuid4()))
        db.exec.assert_not_called()


def test_existing_locked_store_is_visible_but_paused_store_is_not():
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        visible = Store(name="Visible", entity_id=uuid4(), email="visible@example.test", website="https://visible.example.test",
                        is_active=True, is_billing_locked=True)
        paused = Store(name="Paused", entity_id=uuid4(), email="paused@example.test", website="https://paused.example.test",
                       is_active=False, is_billing_locked=True)
        session.add_all([visible, paused])
        session.commit()
        with patch("models.service.store_service.db_session", session):
            assert [store.id for store in StoreService().get_all_active_stores()] == [visible.id]
        with patch.object(subscriptions, "db_session", session):
            subscriptions._sync_store_lock(visible.id, locked=True)
            assert visible.is_billing_locked is False
