"""
Unit-level API tests for core authentication endpoints.

These tests exercise individual endpoints in isolation without relying on
cross-test fixtures or pre-seeded DB state.
"""
from tests._client import client, get_test_otp


def test_send_otp():
    """Test sending OTP to a phone number"""
    response = client.post("/user/send-otp", json={"phone": "+1234567890"})
    assert response.status_code == 200
    assert "message" in response.json()
    assert "OTP sent successfully" in response.json()["message"]


def test_verify_otp_invalid():
    """Test verifying an invalid OTP"""
    # First send OTP
    client.post("/user/send-otp", json={"phone": "+1234567890"})

    # Try to verify with wrong OTP
    response = client.post("/user/verify-otp", json={"phone": "+1234567890", "otp": "000000"})
    assert response.status_code == 400
    assert "Invalid or expired OTP" in response.json()["detail"]


def test_registration_without_phone_verification():
    """Test registration without phone verification should fail"""
    phone = "+9999999999"

    # Send OTP so the user record exists, but do NOT verify it
    client.post("/user/send-otp", json={"phone": phone})

    registration_data = {
        "phone": phone,
        "entity_type": "user",
        "password": "testpassword123",
    }

    response = client.post("/user/register", json=registration_data)
    assert response.status_code == 400
    assert "Phone number not verified" in response.json()["detail"]


def test_complete_registration_flow():
    """Test complete registration flow with OTP verification"""
    phone = "+1234567890"

    # Step 1: Send OTP
    response = client.post("/user/send-otp", json={"phone": phone})
    assert response.status_code == 200

    # Step 2: Read OTP directly from the test DB (the /user/otp endpoint was
    # removed because returning OTPs over HTTP is a security vulnerability).
    otp = get_test_otp(phone)

    # Step 3: Verify OTP
    response = client.post("/user/verify-otp", json={"phone": phone, "otp": otp})
    assert response.status_code == 200
    assert "OTP verified successfully" in response.json()["message"]

    # Step 4: Register user
    registration_data = {
        "phone": phone,
        "entity_type": "store",
        "password": "testpassword123",
    }

    response = client.post("/user/register", json=registration_data)
    assert response.status_code == 200
    assert "id" in response.json()


def test_login():
    """Test user login with phone and password after completing the full registration flow."""
    phone = "+1234567890"

    # Re-run the OTP flow (OTP is cleared after each verification, so we need a fresh one).
    client.post("/user/send-otp", json={"phone": phone})
    otp = get_test_otp(phone)
    client.post("/user/verify-otp", json={"phone": phone, "otp": otp})
    client.post(
        "/user/register",
        json={"phone": phone, "entity_type": "store", "password": "testpassword123"},
    )

    login_data = {
        "phone": phone,
        "password": "testpassword123",
    }

    response = client.post("/user/login", json=login_data)
    assert response.status_code == 200
    assert "token" in response.json()
