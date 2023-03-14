import logging

from fastapi import Depends, FastAPI, HTTPException, status

from api.validators.user_validation import (ChangePasswordPayload,
                                            ChangePasswordResponse,
                                            LoginPayload, LoginResponse,
                                            RegistrationPayload,
                                            RegistrationResponse)
from helpers.jwt import JWT, oauth2_scheme
from models.service.user_service import User

logger = logging.getLogger("groceror")
user_apis = FastAPI()


@user_apis.post("/register", response_model=RegistrationResponse)
async def register(registration_payload: RegistrationPayload):
    logger.info(f"Registering user with payload: {registration_payload}")
    try:
        user_registration_obj = User()
        new_user_id = user_registration_obj.register(**registration_payload.dict())
    except Exception as e:
        logger.exception(f"Error while registering user with exception details {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Issue with registering user",
        )
    else:
        return {"id": new_user_id}


@user_apis.post("/login", response_model=LoginResponse)
async def login(login_payload: LoginPayload):
    logger.info(f"Logging in user with payload: {login_payload}")
    try:
        user_login_obj = User()
        user_id = user_login_obj.login(login_payload)
    except Exception as e:
        logger.exception(f"Error while logging in user with exception details {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Issue with logging user",
        )
    else:
        return {"id": user_id}


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
