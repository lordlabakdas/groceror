import logging

from fastapi import FastAPI

from api.validators.uservalidation import (ChangePasswordPayload,
                                           ChangePasswordResponse,
                                           LoginPayload, LoginResponse,
                                           RegistrationPayload,
                                           RegistrationResponse)
from models.service.registration import User

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


@user_apis.put("changepassword", response_model=ChangePasswordResponse)
async def change_password(change_password_payload: ChangePasswordPayload):
    logger.info(f"Changing password for user with payload: {change_password_payload}")
    user_change_password_obj = User()
    user_change_password_obj.change_password(change_password_payload)
    return {"status": "success"}


@user_apis.get("/logout")
async def logout():
    logger.info("Logging out user")
    user_logout_obj = User()
    user_logout_obj.logout()
    return {"status": "success"}
