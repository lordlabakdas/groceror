import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from loguru import logger

from api.helpers import auth_helper
from api.validators.user_validation import (
    ChangePasswordPayload,
    ChangePasswordResponse,
    LoginPayload,
    LoginResponse,
    MeResponse,
    RegistrationPayload,
    RegistrationResponse,
    SendOTPPayload,
    SendOTPResponse,
    VerifyOTPPayload,
    VerifyOTPResponse,
    ProfilePayload,
    ProfileResponse,
)
from config import JWTConfig
from engine import publisher
from helpers.jwt import JWT, auth_required

from models.entity.phone_verification import PhoneVerification

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# logger = logging.getLogger("groceror")
user_apis = APIRouter(prefix="/user", tags=["user"])


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
        phone: str = payload.get("sub")
        current_user = auth_helper.get_user_by_phone(phone=phone)
        if current_user is None:
            raise credentials_exception
        return current_user
    except Exception:
        raise credentials_exception


@user_apis.post("/send-otp", response_model=SendOTPResponse)
async def send_otp(payload: SendOTPPayload):
    """Send OTP to the provided phone number"""
    logger.info(f"Sending OTP to phone: {payload.phone}")
    try:
        auth_helper.send_otp(phone=payload.phone)
        return {"message": f"OTP sent successfully to {payload.phone}"}
    except Exception as e:
        logger.exception(f"Error sending OTP: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send OTP",
        )


@user_apis.post("/verify-otp", response_model=VerifyOTPResponse)
async def verify_otp(payload: VerifyOTPPayload):
    """Verify OTP for the provided phone number"""
    logger.info(f"Verifying OTP for phone: {payload.phone}")
    try:
        is_valid = auth_helper.verify_otp(phone=payload.phone, otp=payload.otp)
        if is_valid:
            user = auth_helper.get_user_by_phone(phone=payload.phone)
            if user:
                try:
                    publisher.publish_message(
                        event="otp_verified",
                        routing_key=publisher.USER_EVENTS_QUEUE,
                        queue_name=publisher.USER_EVENTS_QUEUE,
                        user_id=str(user.id),
                        phone=payload.phone,
                    )
                except Exception:
                    logger.warning("Failed to publish otp_verified for phone=%s", payload.phone)
            return {"message": "OTP verified successfully"}
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired OTP",
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error verifying OTP: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to verify OTP",
        )


@user_apis.post("/register", response_model=RegistrationResponse)
async def register(registration_payload: RegistrationPayload):
    logger.info(f"Registering user with payload: {registration_payload}")
    try:
        # Check if user already exists (i.e. OTP has been sent)
        if not auth_helper.is_user_exists(phone=registration_payload.phone):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Phone number not found. Please send OTP first.",
            )
        
        # Register the user (this will also verify phone number)
        new_user = auth_helper.register(register_payload=registration_payload.dict())
        
    except HTTPException:
        raise
    except ValueError as e:
        if "Phone number not verified" in str(e):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Phone number not verified. Please verify your phone number first.",
            )
        elif "User with this email already exists" in str(e):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="User already exists",
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e),
            )
    except Exception as e:
        logger.exception(f"Error while registering user with exception details {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Issue with registering user",
        )
    else:
        try:
            publisher.publish_message(
                event="user_registered",
                routing_key=publisher.USER_EVENTS_QUEUE,
                queue_name=publisher.USER_EVENTS_QUEUE,
                user_id=str(new_user.id),
                phone=new_user.phone,
                entity_type=new_user.entity_type,
            )
        except Exception:
            logger.warning("Failed to publish user_registered for user_id=%s", new_user.id)
        return {"id": new_user.id}


@user_apis.get("/me", response_model=MeResponse)
async def get_me(current_user: PhoneVerification = Depends(get_current_user)):
    profile = auth_helper.get_profile(current_user)
    return MeResponse(phone=current_user.phone, entity_type=current_user.entity_type, **profile)


@user_apis.post("/set-profile", response_model=ProfileResponse)
async def set_profile(
    profile_payload: ProfilePayload,
    current_user: PhoneVerification = Depends(get_current_user)
):
    """Set profile for both user and store types"""
    logger.info(f"Setting profile for user type: {current_user.entity_type}")
    
    try:
        # Validate required fields based on entity type
        if current_user.entity_type == "store" and not profile_payload.website:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Website is required for store profiles"
            )
        
        # Set profile based on entity type
        result = auth_helper.set_profile(entity=current_user, profile_payload=profile_payload)
        try:
            publisher.publish_message(
                event="profile_updated",
                routing_key=publisher.USER_EVENTS_QUEUE,
                queue_name=publisher.USER_EVENTS_QUEUE,
                user_id=str(current_user.id),
                profile_id=str(result.id),
                entity_type=current_user.entity_type,
                name=profile_payload.name or "",
                email=profile_payload.email or "",
                location=profile_payload.location or "",
            )
        except Exception:
            logger.warning("Failed to publish profile_updated for user_id=%s", current_user.id)

        entity_type = current_user.entity_type or "user"
        geocoded = None
        if entity_type == "store" and hasattr(result, "latitude"):
            geocoded = result.latitude is not None
        return ProfileResponse(
            message=f"{entity_type.capitalize()} profile updated successfully",
            geocoded=geocoded,
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error while setting profile: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Issue with setting profile",
        )


@user_apis.post("/otp")
async def send_otp_legacy(phone: str):
    """Legacy endpoint for backward compatibility"""
    otp = auth_helper.send_otp(phone=phone)
    return {"otp": otp}


@user_apis.post("/login", response_model=LoginResponse)
async def login(login_payload: LoginPayload):
    logger.info(f"Logging in user with payload: {login_payload.dict()}")

    user = auth_helper.get_user_by_phone(phone=login_payload.phone)
    if not user or not auth_helper.verify_password(
        login_payload.password, user.password
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
        )

    jwt_obj = JWT()
    access_token = jwt_obj.create_token(
        payload={"sub": user.phone, "entity_type": user.entity_type or "user"}
    )
    return {"token": access_token}


@user_apis.put("/change-password", response_model=ChangePasswordResponse)
async def change_password(
    change_password_payload: ChangePasswordPayload,
    current_user: PhoneVerification = Depends(get_current_user),
):
    logger.info(f"Changing password for user with payload: {change_password_payload}")
    # Update the password in the PhoneVerification model
    current_user.password = auth_helper.hash_password(change_password_payload.new_password)  # type: ignore
    from models.db import db_session
    db_session.commit()
    try:
        publisher.publish_message(
            event="password_changed",
            routing_key=publisher.USER_EVENTS_QUEUE,
            queue_name=publisher.USER_EVENTS_QUEUE,
            user_id=str(current_user.id),
            phone=current_user.phone,
        )
    except Exception:
        logger.warning("Failed to publish password_changed for user_id=%s", current_user.id)
    return {"status": "success"}


@user_apis.get("/refresh-token")
async def refresh_token(current_user: PhoneVerification = Depends(get_current_user)):
    """Refresh the JWT token"""
    jwt_obj = JWT()
    access_token = jwt_obj.create_token(
        payload={"sub": current_user.phone, "entity_type": current_user.entity_type or "user"}
    )
    return {"token": access_token}
