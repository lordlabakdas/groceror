"""
Tests that user lifecycle endpoints publish the correct RabbitMQ events.
publisher.publish_message is mocked — no RabbitMQ connection required.
"""
from unittest.mock import patch

from tests._client import client


def _register_user(phone: str) -> None:
    """Helper: full OTP flow so a user is registered and verified."""
    client.post("/user/send-otp", json={"phone": phone})
    otp_resp = client.post("/user/otp", params={"phone": phone})
    otp = otp_resp.json()["otp"]
    client.post("/user/verify-otp", json={"phone": phone, "otp": otp})


def test_register_publishes_user_registered():
    phone = "+15550000001"
    _register_user(phone)
    with patch("api.user_api.publisher.publish_message") as mock_pub:
        resp = client.post("/user/register", json={
            "phone": phone, "entity_type": "user", "password": "pass1234"
        })
    assert resp.status_code == 200
    mock_pub.assert_called_once()
    kw = mock_pub.call_args.kwargs
    assert kw["event"] == "user_registered"
    assert kw["queue_name"] == "user_events_queue"
    assert kw["phone"] == phone
    assert kw["entity_type"] == "user"
    assert "user_id" in kw


def test_verify_otp_publishes_otp_verified():
    phone = "+15550000002"
    client.post("/user/send-otp", json={"phone": phone})
    otp_resp = client.post("/user/otp", params={"phone": phone})
    otp = otp_resp.json()["otp"]
    with patch("api.user_api.publisher.publish_message") as mock_pub:
        resp = client.post("/user/verify-otp", json={"phone": phone, "otp": otp})
    assert resp.status_code == 200
    mock_pub.assert_called_once()
    kw = mock_pub.call_args.kwargs
    assert kw["event"] == "otp_verified"
    assert kw["queue_name"] == "user_events_queue"
    assert kw["phone"] == phone
    assert "user_id" in kw


def test_set_profile_publishes_profile_updated():
    phone = "+15550000003"
    _register_user(phone)
    client.post("/user/register", json={
        "phone": phone, "entity_type": "user", "password": "pass1234"
    })
    login_resp = client.post("/user/login", json={"phone": phone, "password": "pass1234"})
    token = login_resp.json()["token"]
    with patch("api.user_api.publisher.publish_message") as mock_pub:
        resp = client.post(
            "/user/set-profile",
            json={"name": "Alice", "email": "alice@example.com", "location": "NYC"},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 200
    mock_pub.assert_called_once()
    kw = mock_pub.call_args.kwargs
    assert kw["event"] == "profile_updated"
    assert kw["queue_name"] == "user_events_queue"
    assert kw["name"] == "Alice"
    assert "user_id" in kw
    assert kw["profile_id"] is not None
    assert kw["entity_type"] == "user"
    assert kw["email"] == "alice@example.com"
    assert kw["location"] == "NYC"


def test_change_password_publishes_password_changed():
    phone = "+15550000004"
    _register_user(phone)
    client.post("/user/register", json={
        "phone": phone, "entity_type": "user", "password": "pass1234"
    })
    login_resp = client.post("/user/login", json={"phone": phone, "password": "pass1234"})
    token = login_resp.json()["token"]
    with patch("api.user_api.publisher.publish_message") as mock_pub:
        resp = client.put(
            "/user/change-password",
            json={"new_password": "newpass5678"},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 200
    mock_pub.assert_called_once()
    kw = mock_pub.call_args.kwargs
    assert kw["event"] == "password_changed"
    assert kw["queue_name"] == "user_events_queue"
    assert kw["phone"] == phone
    assert "user_id" in kw
