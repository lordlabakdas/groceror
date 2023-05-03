import logging

from fastapi import APIRouter, Depends, HTTPException, status
from firebase_admin import auth as firebase_auth
from google.oauth2 import id_token

from api.helpers import auth_helper
from api.validators.user_validation import (
    ChangePasswordPayload,
    ChangePasswordResponse,
    FirebaseRegistrationPayload,
    FirebaseRegistrationResponse,
    LoginPayload,
    LoginResponse,
    FirebaseLoginPayload,
    FirebaseLoginResponse,
    RegistrationPayload,
    RegistrationResponse,
)
from helpers.jwt import JWT, oauth2_scheme
from models.service.user_service import User


logger = logging.getLogger("groceror")
user_apis = APIRouter()


@user_apis.post("/register", response_model=RegistrationResponse)
async def register(registration_payload: RegistrationPayload):
    logger.info(f"Registering user with payload: {registration_payload}")
    try:
        if not auth_helper.is_user_exists(email=registration_payload.email):
            new_user = auth_helper.register(**registration_payload.dict())
        else:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="User already exists",
            )
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
    logger.info(f"Logging in user with payload: {login_payload.dict()}")

    user = auth_helper.get_user_by_email(email=login_payload.email)
    if not user or not auth_helper.verify_password(
        login_payload.password, user.password
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
        )

    jwt_obj = JWT()
    access_token = jwt_obj.create_token({"sub": user.username})
    return {"token": access_token}


@user_apis.post("/firebase-login", response_model=FirebaseLoginResponse)
async def firebase_login(login_payload: FirebaseLoginPayload):
    logger.info(f"Logging in user with payload: {login_payload.dict()}")
    try:
        auth_user = firebase_auth.authenticate(**login_payload.dict())
        if auth_user:
            token = firebase_auth.create_custom_token(auth_user.uid)
        else:
            # User is not authenticated
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials"
            )
    except firebase_auth.AuthError:
        # Handle authentication error
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials"
        )
    else:
        return {"token": token}

@user_apis.post("/firebase-register", response_model=FirebaseRegistrationResponse)
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

@user_apis.post("/firebase-logout")
async def firebase_logout(token: str):
    try:
        decoded_token = firebase_auth.verify_id_token(token)
        uid = decoded_token['uid']
        firebase_auth.revoke_refresh_tokens(uid)
        return {"message": "User logged out successfully."}
    except firebase_auth.InvalidIdTokenError as e:
        return {"error": str(e)}

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
