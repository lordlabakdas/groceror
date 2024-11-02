from uuid import uuid4

import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from loguru import logger

from api.helpers import auth_helper
from api.helpers.auth_helper import verify_user
from api.validators.user_validation import (ChangePasswordPayload,
                                            ChangePasswordResponse,
                                            LoginPayload, LoginResponse,
                                            RegistrationPayload,
                                            RegistrationResponse, UserResponse)
from config import JWTConfig
from helpers.jwt import JWT

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# logger = logging.getLogger("groceror")
user_apis = APIRouter()


def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(
            token, JWTConfig.JWT_SECRET_KEY, algorithms=[JWTConfig.JWT_ALGORITHM]
        )
        username: str = payload.get("sub")
        current_user = auth_helper.get_user_by_username(username=username)
        if current_user is None:
            raise credentials_exception
    except jwt.JWTError:
        raise credentials_exception


@user_apis.post("/register", response_model=RegistrationResponse)
async def register(registration_payload: RegistrationPayload):
    logger.info(f"Registering user with payload: {registration_payload}")
    verification_token = str(uuid4())
    try:
        if not auth_helper.is_user_exists(email=registration_payload.email):
            new_user = auth_helper.register(
                **registration_payload.dict(), verification_token=verification_token
            )
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
async def change_password(
    change_password_payload: ChangePasswordPayload,
    current_user: str = Depends(get_current_user),
):
    logger.info(f"Changing password for user with payload: {change_password_payload}")
    auth_helper.change_password(current_user, change_password_payload)
    return {"status": "success"}


@user_apis.post("/verify-email/{token}", response_model=UserResponse)
async def verify_email(token: str):
    user = verify_user(token)
    if user:
        return UserResponse.from_orm(user)
    else:
        raise HTTPException(
            status_code=400, detail="Invalid or expired verification token"
        )
