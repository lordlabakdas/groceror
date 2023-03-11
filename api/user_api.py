import logging

from fastapi import FastAPI
from fastapi.security import JWTAuthentication, OAuth2PasswordBearer
from fastapi import Depends, HTTPException

from api.validators.user_validation import (
    ChangePasswordPayload,
    ChangePasswordResponse,
    LoginPayload,
    LoginResponse,
    RegistrationPayload,
    RegistrationResponse,
)
from helpers.jwt import JWT
from models.service.user_service import User

logger = logging.getLogger("groceror")
user_apis = FastAPI()


@user_apis.post("/register", response_model=RegistrationResponse)
async def register(registration_payload: RegistrationPayload):
    logger.info(f"Registering user with payload: {registration_payload}")
    user_registration_obj = User()
    new_user_id = user_registration_obj.register(**registration_payload.dict())
    return {"id": new_user_id}


@user_apis.post("/login", response_model=LoginResponse)
async def login(login_payload: LoginPayload):
    logger.info(f"Logging in user with payload: {login_payload}")
    user_login_obj = User()
    user_id = user_login_obj.login(login_payload)
    return {"id": user_id}


@user_apis.put("change-password", response_model=ChangePasswordResponse)
async def change_password(change_password_payload: ChangePasswordPayload):
    logger.info(f"Changing password for user with payload: {change_password_payload}")
    user_change_password_obj = User()
    user_change_password_obj.change_password(change_password_payload)
    return {"status": "success"}


@user_apis.get("/logout")
def logout(
    token: str = Depends(OAuth2PasswordBearer(tokenUrl="token"))
):
    jwt_obj = JWT()
    payload = jwt_obj.decode_token(token=token)
    if payload is None:
        raise HTTPException(status_code=401, detail="Invalid token")
    return {"detail": "Logout successful"}
