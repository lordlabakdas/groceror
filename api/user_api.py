import logging

from fastapi import APIRouter, HTTPException, status

from api.helpers import auth_helper
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
from loguru import logger


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


@user_apis.put("/change-password", response_model=ChangePasswordResponse)
async def change_password(change_password_payload: ChangePasswordPayload):
    logger.info(f"Changing password for user with payload: {change_password_payload}")
    user_change_password_obj = User()
    user_change_password_obj.change_password(change_password_payload)
    return {"status": "success"}


# logger = logging.getLogger(__name__)

# @user_apis.get("/logout")
# def logout():
#     logger.info("Logging out user")
#     flask_login.logout_user()
#     flask.flash("You have been logged out.")
#     return {"detail": "Logout successful"}
