"""
Coverage for the "leftover gaps" group: SSE, Google login, JWT error
branches, user_api error branches, custom_openapi, and a handful of plain
unit tests for entity/service code that's easiest to exercise directly
rather than through HTTP (helpers/exceptions.py, models/entity/cart_entity.py,
models/entity/store_entity.py, models/service/cart_service.py).

Fixtures come from tests/integration/conftest.py (module-scoped, shared
across tests/integration/*.py) and tests/integration/helpers.py. New
accounts needed locally use a private phone prefix (+1563{_suffix}0N) to
avoid collisions with the other new test files in this suite.
"""
import uuid
from unittest.mock import MagicMock, patch

import jwt
import pytest

from tests.integration.helpers import client, _headers, _login, _otp_and_verify, _register

_suffix = str(uuid.uuid4().int)[:6]


def _new_user_account(tag: str) -> str:
    phone = f"+1563{_suffix}{tag}"
    _otp_and_verify(phone)
    _register(phone, "user")
    token = _login(phone)
    # _resolve_channel() (api/sse_api.py) and get_profile() both look up the
    # User row by entity_id, which only exists once a profile has been set.
    r = client.post(
        "/user/set-profile",
        json={"name": "SSE Test User", "email": f"sse-{tag}@example.com"},
        headers=_headers(token),
    )
    assert r.status_code == 200, r.text
    return token


# ─────────────────────────────────────────────────────────────────────────────
# api/user_api.py — remaining error branches
# ─────────────────────────────────────────────────────────────────────────────

class TestUserApiGaps:

    def test_get_current_user_valid_jwt_unknown_phone_401(self):
        """Line 52: token decodes fine, but no PhoneVerification matches."""
        from config import JWTConfig
        token = jwt.encode(
            {"sub": "+10000000000_does_not_exist"},
            JWTConfig.JWT_SECRET_KEY,
            algorithm=JWTConfig.JWT_ALGORITHM,
        )
        r = client.get("/user/me", headers=_headers(token))
        assert r.status_code == 401

    def test_send_otp_failure_returns_500(self):
        """Lines 65-67."""
        with patch("api.user_api.auth_helper.send_otp", side_effect=RuntimeError("boom")):
            r = client.post("/user/send-otp", json={"phone": "+15559990001"})
        assert r.status_code == 500
        assert r.json()["detail"] == "Failed to send OTP"

    def test_verify_otp_failure_returns_500(self):
        """Lines 88-90."""
        with patch("api.user_api.auth_helper.verify_otp", side_effect=RuntimeError("boom")):
            r = client.post("/user/verify-otp", json={"phone": "+15559990002", "otp": "000000"})
        assert r.status_code == 500
        assert r.json()["detail"] == "Failed to verify OTP"

    def test_register_email_already_exists_conflict(self):
        """Lines 118-122. auth_helper.register() doesn't currently raise this
        message for any real input, so the branch is exercised via a mock —
        it's dead-under-current-behavior but still live code worth covering."""
        phone = "+15559990003"
        _otp_and_verify(phone)
        with patch(
            "api.user_api.auth_helper.register",
            side_effect=ValueError("User with this email already exists"),
        ):
            r = client.post(
                "/user/register",
                json={"phone": phone, "entity_type": "user", "password": "pass1234"},
            )
        assert r.status_code == 409
        assert r.json()["detail"] == "User already exists"

    def test_register_generic_exception_500(self):
        """Lines 128-133."""
        phone = "+15559990004"
        _otp_and_verify(phone)
        with patch("api.user_api.auth_helper.register", side_effect=RuntimeError("boom")):
            r = client.post(
                "/user/register",
                json={"phone": phone, "entity_type": "user", "password": "pass1234"},
            )
        assert r.status_code == 500
        assert r.json()["detail"] == "Issue with registering user"

    def test_get_me(self):
        """Lines 140-141."""
        token = _new_user_account("01")
        r = client.get("/user/me", headers=_headers(token))
        assert r.status_code == 200
        body = r.json()
        assert body["entity_type"] == "user"
        assert "phone" in body

    def test_set_profile_failure_500(self):
        """Lines 165-169."""
        token = _new_user_account("02")
        with patch("api.user_api.auth_helper.set_profile", side_effect=RuntimeError("boom")):
            r = client.post(
                "/user/set-profile",
                json={"name": "X", "email": "x@example.com"},
                headers=_headers(token),
            )
        assert r.status_code == 500
        assert r.json()["detail"] == "Issue with setting profile"


# ─────────────────────────────────────────────────────────────────────────────
# api/google_login.py
# ─────────────────────────────────────────────────────────────────────────────

class TestGoogleLogin:

    def test_invalid_token_400(self):
        with patch("api.google_login.id_token.verify_oauth2_token", side_effect=ValueError("bad token")):
            r = client.post("/login", params={"token": "garbage"})
        assert r.status_code == 400
        assert r.json()["detail"] == "Invalid Google token"

    def test_valid_token_success(self):
        with patch(
            "api.google_login.id_token.verify_oauth2_token",
            return_value={"email": "someone@gmail.com"},
        ):
            r = client.post("/login", params={"token": "fake-but-valid"})
        assert r.status_code == 200
        assert "someone@gmail.com" in r.json()["message"]


# ─────────────────────────────────────────────────────────────────────────────
# helpers/jwt.py — decode_token error branches
# ─────────────────────────────────────────────────────────────────────────────

class TestJWTDecode:

    def test_decode_expired_token_raises_401(self):
        from helpers.jwt import JWT
        from config import JWTConfig
        import datetime as dt

        expired = jwt.encode(
            {"sub": "+15550001111", "exp": dt.datetime.utcnow() - dt.timedelta(hours=1)},
            JWTConfig.JWT_SECRET_KEY,
            algorithm=JWTConfig.JWT_ALGORITHM,
        )
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            JWT().decode_token(expired)
        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == "Token has expired"

    def test_decode_garbage_token_raises_401(self):
        from helpers.jwt import JWT
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            JWT().decode_token("not.a.validtoken")
        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == "Invalid token"

    def test_decode_unexpected_error_raises_401(self):
        """Lines 81-85: any non-PyJWT exception during decode is caught too."""
        from helpers.jwt import JWT
        from fastapi import HTTPException
        with patch("helpers.jwt.jwt.decode", side_effect=TypeError("unexpected")):
            with pytest.raises(HTTPException) as exc_info:
                JWT().decode_token("irrelevant")
        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == "Error decoding token"

    def test_auth_required_dependency_rejects_invalid_token(self):
        r = client.get("/dashboard/", headers=_headers("not-a-real-token"))
        assert r.status_code == 401


# ─────────────────────────────────────────────────────────────────────────────
# helpers/exceptions.py
# ─────────────────────────────────────────────────────────────────────────────

class TestGrocerorError:

    def test_str_format(self):
        from helpers.exceptions import GrocerorError
        err = GrocerorError(entity="user", action="create", message="failed")
        assert str(err) == "USER CREATE failed"
        assert err.entity == "user"
        assert err.action == "create"
        assert err.message == "failed"


# ─────────────────────────────────────────────────────────────────────────────
# models/entity/cart_entity.py — plain in-memory methods, no DB needed
# ─────────────────────────────────────────────────────────────────────────────

class TestCartEntityMethods:

    def _cart_with_items(self):
        from models.entity.cart_entity import CartEntity
        cart = CartEntity(user_id=uuid.uuid4(), store_id=uuid.uuid4())
        cart.items = []
        item1 = MagicMock(price=2.0, quantity=3)
        item2 = MagicMock(price=1.5, quantity=2)
        cart.items = [item1, item2]
        return cart, item1, item2

    def test_add_item(self):
        from models.entity.cart_entity import CartEntity
        cart = CartEntity(user_id=uuid.uuid4(), store_id=uuid.uuid4())
        cart.items = []
        new_item = MagicMock(price=3.0, quantity=2)
        cart.add_item(new_item)
        assert new_item in cart.items
        assert cart.total_price == 6.0
        assert cart.total_quantity == 2

    def test_remove_item(self):
        cart, item1, item2 = self._cart_with_items()
        cart.total_price = item1.price * item1.quantity + item2.price * item2.quantity
        cart.total_quantity = item1.quantity + item2.quantity
        cart.remove_item(item1)
        assert item1 not in cart.items
        assert cart.total_price == pytest.approx(3.0)
        assert cart.total_quantity == 2

    def test_clear(self):
        cart, _, _ = self._cart_with_items()
        cart.clear()
        assert cart.items == []
        assert cart.total_price == 0.0
        assert cart.total_quantity == 0

    def test_get_total_price(self):
        cart, item1, item2 = self._cart_with_items()
        assert cart.get_total_price() == pytest.approx(2.0 * 3 + 1.5 * 2)

    def test_get_total_quantity(self):
        cart, item1, item2 = self._cart_with_items()
        assert cart.get_total_quantity() == 5

    def test_get_items(self):
        cart, item1, item2 = self._cart_with_items()
        assert cart.get_items() == [item1, item2]


# ─────────────────────────────────────────────────────────────────────────────
# models/entity/store_entity.py — plain methods
# ─────────────────────────────────────────────────────────────────────────────

class TestStoreEntityMethods:

    def _store(self, **kwargs):
        from models.entity.store_entity import Store
        defaults = dict(
            name="Test Store", email="s@example.com", website="https://s.example.com",
            entity_id=uuid.uuid4(), is_active=True,
        )
        defaults.update(kwargs)
        return Store(**defaults)

    def test_repr_and_str(self):
        store = self._store(name="Cool Store")
        assert "Cool Store" in repr(store)
        assert str(store) == "Cool Store"

    def test_hash(self):
        store = self._store()
        assert hash(store) == hash(store.id)

    def test_active_and_is_inactive(self):
        active_store = self._store(is_active=True)
        inactive_store = self._store(is_active=False)
        assert active_store.active() is True
        assert active_store.is_inactive() is False
        assert inactive_store.active() is False
        assert inactive_store.is_inactive() is True

    def test_get_email(self):
        store = self._store(email="hello@store.com")
        assert store.get_email() == "hello@store.com"


# ─────────────────────────────────────────────────────────────────────────────
# models/service/cart_service.py — remaining branches, mocked db_session
# ─────────────────────────────────────────────────────────────────────────────

class TestCartServiceGaps:

    def test_add_item_inventory_not_found_raises_404(self):
        from models.service.cart_service import CartService
        from fastapi import HTTPException

        user = MagicMock(id=uuid.uuid4())
        with patch("models.service.cart_service.db_session") as mock_db:
            mock_db.exec.return_value.first.return_value = None
            svc = CartService(user)
            item_data = MagicMock(inventory_id=uuid.uuid4(), quantity=1)
            with pytest.raises(HTTPException) as exc_info:
                svc.add_item(uuid.uuid4(), item_data)
            assert exc_info.value.status_code == 404

    def test_add_item_insufficient_quantity_raises_400(self):
        from models.service.cart_service import CartService
        from fastapi import HTTPException

        user = MagicMock(id=uuid.uuid4())
        inventory = MagicMock(quantity=1)
        with patch("models.service.cart_service.db_session") as mock_db:
            mock_db.exec.return_value.first.return_value = inventory
            svc = CartService(user)
            item_data = MagicMock(inventory_id=uuid.uuid4(), quantity=5)
            with pytest.raises(HTTPException) as exc_info:
                svc.add_item(uuid.uuid4(), item_data)
            assert exc_info.value.status_code == 400

    def test_add_item_unexpected_error_rolls_back_and_raises_400(self):
        """Lines 72-74: generic Exception path in add_item."""
        from models.service.cart_service import CartService
        from fastapi import HTTPException

        user = MagicMock(id=uuid.uuid4())
        inventory = MagicMock(quantity=10)
        with patch("models.service.cart_service.db_session") as mock_db:
            mock_db.exec.return_value.first.return_value = inventory
            mock_db.add.side_effect = RuntimeError("db exploded")
            svc = CartService(user)
            item_data = MagicMock(inventory_id=uuid.uuid4(), quantity=1, model_dump=lambda: {"inventory_id": uuid.uuid4(), "quantity": 1})
            with pytest.raises(HTTPException) as exc_info:
                svc.add_item(uuid.uuid4(), item_data)
            assert exc_info.value.status_code == 400
            mock_db.rollback.assert_called_once()

    def test_update_item_not_found_raises_404(self):
        """Line 101."""
        from models.service.cart_service import CartService
        from fastapi import HTTPException

        user = MagicMock(id=uuid.uuid4())
        cart = MagicMock(id=uuid.uuid4(), store_id=uuid.uuid4())
        with patch.object(CartService, "get_active_cart", return_value=cart):
            with patch("models.service.cart_service.db_session") as mock_db:
                mock_db.exec.return_value.first.return_value = None
                svc = CartService(user)
                item_data = MagicMock(quantity=None)
                with pytest.raises(HTTPException) as exc_info:
                    svc.update_item(uuid.uuid4(), uuid.uuid4(), item_data)
                assert exc_info.value.status_code == 404

    def test_update_item_unexpected_error_rolls_back(self):
        """Lines 119-123."""
        from models.service.cart_service import CartService
        from fastapi import HTTPException

        user = MagicMock(id=uuid.uuid4())
        cart = MagicMock(id=uuid.uuid4(), store_id=uuid.uuid4())
        cart_item = MagicMock(price=1.0, quantity=1)
        with patch.object(CartService, "get_active_cart", return_value=cart):
            with patch("models.service.cart_service.db_session") as mock_db:
                mock_db.exec.return_value.first.return_value = cart_item
                mock_db.commit.side_effect = RuntimeError("boom")
                svc = CartService(user)
                item_data = MagicMock(quantity=2, model_dump=lambda exclude_unset=True: {"quantity": 2})
                with pytest.raises(HTTPException) as exc_info:
                    svc.update_item(uuid.uuid4(), uuid.uuid4(), item_data)
                assert exc_info.value.status_code == 400
                mock_db.rollback.assert_called_once()

    def test_remove_item_not_found_raises_404(self):
        """Lines 151-153 region: not-found branch of remove_item (line 140 area, plus surrounding)."""
        from models.service.cart_service import CartService
        from fastapi import HTTPException

        user = MagicMock(id=uuid.uuid4())
        cart = MagicMock(id=uuid.uuid4())
        with patch.object(CartService, "get_active_cart", return_value=cart):
            with patch("models.service.cart_service.db_session") as mock_db:
                mock_db.exec.return_value.first.return_value = None
                svc = CartService(user)
                with pytest.raises(HTTPException) as exc_info:
                    svc.remove_item(uuid.uuid4(), uuid.uuid4())
                assert exc_info.value.status_code == 404

    def test_remove_item_unexpected_error_rolls_back(self):
        from models.service.cart_service import CartService
        from fastapi import HTTPException

        user = MagicMock(id=uuid.uuid4())
        cart = MagicMock(id=uuid.uuid4())
        cart_item = MagicMock(price=1.0, quantity=1)
        with patch.object(CartService, "get_active_cart", return_value=cart):
            with patch("models.service.cart_service.db_session") as mock_db:
                mock_db.exec.return_value.first.return_value = cart_item
                mock_db.commit.side_effect = RuntimeError("boom")
                svc = CartService(user)
                with pytest.raises(HTTPException) as exc_info:
                    svc.remove_item(uuid.uuid4(), uuid.uuid4())
                assert exc_info.value.status_code == 400
                mock_db.rollback.assert_called_once()

    def test_clear_unexpected_error_rolls_back(self):
        """Lines 173-175, 181, 184 region."""
        from models.service.cart_service import CartService
        from fastapi import HTTPException

        user = MagicMock(id=uuid.uuid4())
        cart = MagicMock(id=uuid.uuid4())
        with patch.object(CartService, "get_active_cart", return_value=cart):
            with patch("models.service.cart_service.db_session") as mock_db:
                mock_db.exec.return_value.all.return_value = []
                mock_db.commit.side_effect = RuntimeError("boom")
                svc = CartService(user)
                with pytest.raises(HTTPException) as exc_info:
                    svc.clear(uuid.uuid4())
                assert exc_info.value.status_code == 400
                mock_db.rollback.assert_called_once()

    def test_get_total_price_and_quantity(self):
        """Lines 181, 184."""
        from models.service.cart_service import CartService
        user = MagicMock(id=uuid.uuid4())
        cart = MagicMock(total_price=12.5, total_quantity=3)
        with patch.object(CartService, "get_active_cart", return_value=cart):
            svc = CartService(user)
            assert svc.get_total_price(uuid.uuid4()) == 12.5
            assert svc.get_total_quantity(uuid.uuid4()) == 3


# ─────────────────────────────────────────────────────────────────────────────
# api/sse_bus.py — direct unit-style tests (no DB, no HTTP)
# ─────────────────────────────────────────────────────────────────────────────

class TestSSEBus:

    def test_publish_noop_when_loop_not_set(self):
        import api.sse_bus as bus
        original_loop = bus._loop
        try:
            bus._loop = None
            # Must not raise even with no loop and no subscribers.
            bus.publish("some-channel", "event", {"a": 1})
        finally:
            bus._loop = original_loop

    def test_subscribe_unsubscribe_publish_delivers_to_queue(self):
        import asyncio
        import api.sse_bus as bus

        async def run():
            loop = asyncio.get_event_loop()
            bus.set_loop(loop)
            channel = f"chan-{uuid.uuid4()}"
            q = bus.subscribe(channel)
            bus.publish(channel, "ping", {"x": 1})
            msg = await asyncio.wait_for(q.get(), timeout=1)
            assert msg == {"event": "ping", "data": {"x": 1}}
            bus.unsubscribe(channel, q)
            # Unsubscribing twice must not raise (ValueError is swallowed).
            bus.unsubscribe(channel, q)

        asyncio.run(run())


# ─────────────────────────────────────────────────────────────────────────────
# api/sse_api.py
# ─────────────────────────────────────────────────────────────────────────────

class TestSSEStream:

    def test_stream_rejects_invalid_token(self):
        r = client.get("/sse/stream", params={"token": "garbage-token"})
        assert r.status_code == 401

    def test_resolve_channel_returns_none_for_unknown_phone(self):
        from api.sse_api import _resolve_channel
        from config import JWTConfig
        token = jwt.encode(
            {"sub": "+19998887777_unknown"}, JWTConfig.JWT_SECRET_KEY, algorithm=JWTConfig.JWT_ALGORITHM,
        )
        assert _resolve_channel(token) is None

    def test_resolve_channel_returns_none_for_garbage_token(self):
        from api.sse_api import _resolve_channel
        assert _resolve_channel("not-a-token") is None

    def test_resolve_channel_resolves_user_channel(self):
        token = _new_user_account("03")
        from api.sse_api import _resolve_channel
        channel = _resolve_channel(token)
        assert channel is not None
        uuid.UUID(channel)  # must be a valid UUID string

    def test_sse_stream_route_accepts_valid_token(self):
        """Confirm the route wiring (auth + StreamingResponse construction)
        works, by calling the route function directly rather than through
        TestClient's HTTP layer — TestClient's streaming support for
        never-ending generators (this endpoint only yields its first byte
        after a 25s keepalive) hangs indefinitely rather than returning
        once headers are available, and previously left the suite stuck."""
        import asyncio
        from fastapi.responses import StreamingResponse
        from api.sse_api import sse_stream

        token = _new_user_account("04")

        async def run():
            response = await sse_stream(token=token)
            assert isinstance(response, StreamingResponse)
            assert response.media_type == "text/event-stream"
            assert response.headers["Cache-Control"] == "no-cache"
            # Don't iterate response.body_iterator — that's _event_stream's
            # infinite loop, covered separately and safely in the test above.

        asyncio.run(run())

    def test_event_stream_yields_published_message_and_cleans_up(self):
        """Exercise _event_stream directly — the generator that backs the
        route — rather than through a live HTTP connection."""
        import asyncio
        import api.sse_bus as bus
        from api.sse_api import _event_stream

        async def run():
            channel = f"chan-{uuid.uuid4()}"
            q = bus.subscribe(channel)
            q.put_nowait({"event": "test_event", "data": {"hello": "world"}})

            agen = _event_stream(channel, q)
            chunk = await agen.__anext__()
            assert "test_event" in chunk
            assert "hello" in chunk

            # Closing the generator early must hit the finally: unsubscribe()
            # branch without raising.
            await agen.aclose()
            assert q not in bus._subscribers[channel]

        asyncio.run(run())


# ─────────────────────────────────────────────────────────────────────────────
# main.py — custom_openapi()
# ─────────────────────────────────────────────────────────────────────────────

class TestCustomOpenAPI:

    def test_openapi_schema_has_bearer_auth(self):
        r = client.get("/openapi.json")
        assert r.status_code == 200
        schema = r.json()
        assert schema["components"]["securitySchemes"]["BearerAuth"]["type"] == "http"
        # Every path should have the BearerAuth security requirement applied.
        some_path = next(iter(schema["paths"].values()))
        some_method = next(iter(some_path.values()))
        assert {"BearerAuth": []} in some_method["security"]

    def test_openapi_schema_is_cached(self):
        """Second call hits the `if app.openapi_schema: return` branch."""
        r1 = client.get("/openapi.json")
        r2 = client.get("/openapi.json")
        assert r1.json() == r2.json()
