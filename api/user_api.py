import logging

from fastapi import APIRouter, Depends, FastAPI, HTTPException, status
from firebase_admin import auth
from google.oauth2 import id_token

from api.helpers import auth_helper
from api.validators.user_validation import (ChangePasswordPayload,
                                            ChangePasswordResponse,
                                            LoginPayload, LoginResponse,
                                            RegistrationPayload,
                                            RegistrationResponse)
from helpers.jwt import JWT, oauth2_scheme
from models.service.user_service import User

logger = logging.getLogger("groceror")
user_apis = APIRouter()


@user_apis.post("/register", response_model=RegistrationResponse)
async def register(registration_payload: RegistrationPayload):
    logger.info(f"Registering user with payload: {registration_payload}")
    try:
        new_user = auth_helper.register(**registration_payload.dict())
    except Exception as e:
        logger.exception(f"Error while registering user with exception details {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Issue with registering user",
        )
    else:
        return {"id": new_user.id}


@user_apis.post("/login", response_model=LoginResponse)
async def login(login_payload: LoginPayload):
    logger.info(f"Logging in user with payload: {login_payload,dict()}")
    try:
        user = auth.get_user_by_email(email=login_payload.email)
        if not user:
            return {"success": False}
        auth_user = auth.authenticate(**login_payload.dict())
        if auth_user:
            return {"token": auth.crete_custom_token(auth_user.uid)}
        else:
            # User is not authenticated
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials"
            )
    except auth.AuthError:
        # Handle authentication error
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials"
        )


@user_apis.put("change-password", response_model=ChangePasswordResponse)
async def change_password(change_password_payload: ChangePasswordPayload):
    logger.info(f"Changing password for user with payload: {change_password_payload}")
    user_change_password_obj = User()
    user_change_password_obj.change_password(change_password_payload)
    return {"status": "success"}


@user_apis.get("/logout")
def logout(token: str = Depends(oauth2_scheme)):
    jwt_obj = JWT()
    payload = jwt_obj.decode_token(token=token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
        )
    return {"detail": "Logout successful"}


@user_apis.post("/google/login")
async def google_login(token: str):
    try:
        # Verify token and return user ID
        id_info = id_token.verify_oauth2_token(token, None)
    except ValueError:
        # Invalid token
        raise HTTPException(status_code=400, detail="Invalid Google token")
    else:
        return {"message": f"Logged in with Google as {id_info['email']}"}
