# OTP-Based User Registration Flow

This document describes the new OTP (One-Time Password) verification process for user registration.

## Overview

The registration process now requires phone number verification through OTP before a user account can be created. This adds an extra layer of security and ensures that users provide valid phone numbers.

## Registration Flow

### Step 1: Send OTP
**Endpoint:** `POST /user/send-otp`

**Request:**
```json
{
    "phone": "+1234567890"
}
```

**Response:**
```json
{
    "message": "OTP sent successfully to +1234567890"
}
```

### Step 2: Verify OTP
**Endpoint:** `POST /user/verify-otp`

**Request:**
```json
{
    "phone": "+1234567890",
    "otp": "123456"
}
```

**Response:**
```json
{
    "message": "OTP verified successfully"
}
```

### Step 3: Complete Registration
**Endpoint:** `POST /user/register`

**Request:**
```json
{

    "phone": "+1234567890",
    "entity_type": "store",
    "password": "securepassword123"
}
```

**Response:**
```json
{
    "id": "id-of-created-user"
}
```

## Error Handling

### Phone Not Verified
If a user tries to register without verifying their phone number:
```json
{
    "detail": "Phone number not verified. Please verify your phone number first."
}
```

### Invalid OTP
If an invalid or expired OTP is provided:
```json
{
    "detail": "Invalid or expired OTP"
}
```

### User Already Exists
If a user with the same email already exists:
```json
{
    "detail": "User already exists"
}
```

## OTP Features

- **Length:** 6 digits
- **Expiration:** 10 minutes
- **Storage:** Temporarily stored in database with expiration timestamp
- **Verification:** Clears OTP data after successful verification

## Database Changes

The `User` entity has been updated with the following new fields:
- `phone`: Optional phone number
- `is_phone_verified`: Boolean flag indicating if phone is verified
- `otp`: Temporary OTP storage
- `otp_expires_at`: OTP expiration timestamp

## Security Considerations

1. **OTP Expiration:** OTPs expire after 10 minutes for security
2. **One-time Use:** OTPs are cleared after successful verification
3. **Phone Verification:** Registration requires verified phone number
4. **Temporary Storage:** OTP data is not permanently stored

## Future Enhancements

- Integration with actual SMS service (Twilio, AWS SNS, etc.)
- Rate limiting for OTP requests
- Multiple OTP attempts tracking
- SMS delivery status tracking

## Testing

Use the provided test cases in `tests/unit/test_apis.py` to verify the OTP functionality:

```bash
venv/bin/pytest tests/unit/test_apis.py -v
```

Integration tests (`tests/integration/test_platform.py`) exercise the full `send-otp` → `verify-otp` → `register` flow against a real request/response cycle. Since `/user/send-otp` no longer returns the OTP in the response body (see below), those tests read it back from the test DB via `tests.integration.helpers.get_test_otp(phone)` (re-exported from `tests/_client.py`) instead.

## Legacy Support

The original `/user/otp` endpoint (which returned the OTP directly in the response, for testability) has been **removed** — it leaked OTPs over HTTP. Use `POST /user/send-otp` instead; it returns only `{"message": "..."}"`.