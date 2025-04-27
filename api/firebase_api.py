import logging

from fastapi import APIRouter, HTTPException, status
from firebase_admin import auth as firebase_auth
from google.oauth2 import id_token

from api.validators.user_validation import (ChangePasswordPayload,
                                            ChangePasswordResponse,
                                            FirebaseLoginPayload,
                                            FirebaseLoginResponse,
                                            FirebaseRegistrationPayload,
                                            FirebaseRegistrationResponse)
from models.service.user_service import User

logger = logging.getLogger("groceror")
firebase_apis = APIRouter()


@firebase_apis.post("/register", response_model=FirebaseRegistrationResponse)
async def firebase_register(login_payload: FirebaseRegistrationPayload):
    logger.info(f"Logging in user with payload: {login_payload.dict()}")
    try:
        auth_user = firebase_auth.create_user(**login_payload.dict())
    except firebase_auth.EmailAlreadyExistsError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials"
        )
    else:
        return {"user_id": auth_user.uid}


@firebase_apis.post("/login", response_model=FirebaseLoginResponse)
async def firebase_login(login_payload: FirebaseLoginPayload):
    logger.info(f"Logging in user with payload: {login_payload.dict()}")
    try:
        user = firebase_auth.get_user_by_email(login_payload.email)
        if user:
            token = firebase_auth.create_custom_token(user.uid)
        else:
            # User is not authenticated
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials"
            )
    except Exception as e:
        # Handle authentication error
        print(f"Error while authenticating user with exception details {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials"
        )
    else:
        return {"token": token}


@firebase_apis.put("change-password", response_model=ChangePasswordResponse)
async def change_password(change_password_payload: ChangePasswordPayload):
    logger.info(f"Changing password for user with payload: {change_password_payload}")
    User()
    user_change_password_obj.change_password(change_password_payload)
    return {"status": "success"}


@firebase_apis.post("/logout")
async def firebase_logout(token: str):
    try:
        decoded_token = firebase_auth.verify_id_token(token)
        uid = decoded_token["uid"]
        firebase_auth.revoke_refresh_tokens(uid)
        return {"message": "User logged out successfully."}
    except firebase_auth.InvalidIdTokenError as e:
        return {"error": str(e)}


@firebase_apis.post("/google/login")
async def google_login(token: str):
    try:
        # Verify token and return user ID
        id_info = id_token.verify_oauth2_token(token, None)
    except ValueError:
        # Invalid token
        raise HTTPException(status_code=400, detail="Invalid Google token")
    else:
        return {"message": f"Logged in with Google as {id_info['email']}"}
