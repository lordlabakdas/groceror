import json
import os
import random
import string
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from typing import Optional, Tuple

import boto3
from botocore.exceptions import ClientError
from firebase_admin import auth as firebase_auth
from google.auth.transport import requests
from google.oauth2 import id_token
from passlib.context import CryptContext
from sqlmodel import select

from api.validators.user_validation import ChangePasswordPayload, UserProfilePayload, StoreProfilePayload, ProfilePayload
from models.db import db_session
from models.entity.phone_verification import PhoneVerification
from models.entity.user_entity import User, UserType
from models.entity.store_entity import Store


def validate_google_token(token, client_id):
    try:
        idinfo = id_token.verify_oauth2_token(token, requests.Request(), client_id)

        if "email" not in idinfo:
            raise ValueError("Email not present in token")

        return idinfo

    except ValueError:
        return None


def register(register_payload: dict):
    user_by_phone = get_user_by_phone(register_payload["phone"])
    if not user_by_phone:
        raise ValueError("User not found")
    if not user_by_phone.is_phone_verified:
        raise ValueError("Phone number not verified")

    user = user_by_phone
    user.entity_type = register_payload["entity_type"].value
    user.password = hash_password(register_payload["password"])

    db_session.commit()
    return user


def get_user_by_email(email: str):
    return db_session.exec(select(User).where(User.email == email)).first()


def get_user_by_id(user_id: str):
    return db_session.exec(select(User).where(User.id == user_id)).first()


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def is_user_exists(phone: str) -> bool:
    return get_user_by_phone(phone) is not None


def register_firebase_user(email: str, password: str):
    try:
        user = firebase_auth.create_user(email=email, password=password)
    except firebase_auth.EmailAlreadyExistsError as e:
        raise e
    else:
        return user.uid


def change_password(user: User, change_password_payload: ChangePasswordPayload):
    user.password = hash_password(change_password_payload.new_password)
    db_session.commit()
    return user


def set_user_profile(entity: PhoneVerification, profile_payload: UserProfilePayload):
    """Set user profile for regular users."""
    user = db_session.exec(select(User).where(User.entity_id == entity.id)).first()

    if user:
        user.name = profile_payload.name
        user.email = profile_payload.email
        user.location = profile_payload.location
        user.updated_at = datetime.utcnow()
    else:
        user = User(
            name=profile_payload.name,
            email=profile_payload.email,
            location=profile_payload.location,
            entity_id=entity.id,  # type: ignore
            is_active=True,
        )
        db_session.add(user)

    db_session.commit()
    return user


def geocode_location(location: str) -> Optional[Tuple[float, float]]:
    """Return (latitude, longitude) for a location string using Nominatim, or None."""
    try:
        params = urllib.parse.urlencode({"q": location, "format": "json", "limit": 1})
        req = urllib.request.Request(
            f"https://nominatim.openstreetmap.org/search?{params}",
            headers={"User-Agent": "groceror/1.0"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            results = json.loads(resp.read())
        if results:
            return float(results[0]["lat"]), float(results[0]["lon"])
    except Exception:
        pass
    return None


def set_store_profile(entity: PhoneVerification, profile_payload: StoreProfilePayload):
    """Set store profile for store users."""
    store = db_session.exec(select(Store).where(Store.entity_id == entity.id)).first()

    coords = geocode_location(profile_payload.location) if profile_payload.location else None

    if store:
        store.name = profile_payload.name
        store.email = profile_payload.email
        store.website = profile_payload.website
        store.location = profile_payload.location
        store.updated_at = datetime.utcnow()
        if coords:
            store.latitude, store.longitude = coords
    else:
        lat, lon = coords if coords else (None, None)
        store = Store(
            name=profile_payload.name,
            email=profile_payload.email,
            website=profile_payload.website,
            location=profile_payload.location,
            entity_id=entity.id,  # type: ignore
            is_active=True,
            latitude=lat,
            longitude=lon,
        )
        db_session.add(store)

    db_session.commit()
    return store


def set_profile(entity: PhoneVerification, profile_payload: ProfilePayload):
    """Set profile based on entity type."""
    if entity.entity_type == "store":
        store_payload = StoreProfilePayload(
            name=profile_payload.name,
            email=profile_payload.email,
            website=profile_payload.website or "",
            location=profile_payload.location,
        )
        return set_store_profile(entity, store_payload)
    else:
        user_payload = UserProfilePayload(
            name=profile_payload.name,
            email=profile_payload.email,
            location=profile_payload.location,
        )
        return set_user_profile(entity, user_payload)


def get_profile(entity: PhoneVerification) -> dict:
    """Return profile fields for the entity's User or Store record."""
    if entity.entity_type == "store":
        store = db_session.exec(select(Store).where(Store.entity_id == entity.id)).first()
        if store:
            return {"name": store.name, "email": store.email,
                    "location": store.location, "website": store.website}
        return {"name": None, "email": None, "location": None, "website": None}
    else:
        user = db_session.exec(select(User).where(User.entity_id == entity.id)).first()
        if user:
            return {"name": user.name, "email": user.email, "location": user.location}
        return {"name": None, "email": None, "location": None}


def generate_otp(length: int = 6) -> str:
    """Generate a random OTP of specified length."""
    return ''.join(random.choices(string.digits, k=length))


def send_otp(phone: str) -> str:
    """Generate and store OTP for the given phone number."""
    otp = generate_otp(6)
    expires_at = datetime.utcnow() + timedelta(minutes=10)

    user = db_session.exec(
        select(PhoneVerification).where(PhoneVerification.phone == phone)
    ).first()

    if user:
        user.otp = otp
        user.otp_expires_at = expires_at
        user.is_phone_verified = False
    else:
        user = PhoneVerification(
            phone=phone,
            otp=otp,
            otp_expires_at=expires_at,
            is_phone_verified=False,
            password="",
            entity_type="user",
        )
        db_session.add(user)

    db_session.commit()

    # In production, send via SNS: send_sms_via_sns(phone, f"Your OTP is: {otp}")
    print(f"OTP for {phone}: {otp}")

    return otp


def verify_otp(phone: str, otp: str) -> bool:
    """Verify OTP for the given phone number."""
    user = db_session.exec(
        select(PhoneVerification).where(PhoneVerification.phone == phone)
    ).first()

    if not user or not user.otp:
        return False

    if user.otp_expires_at and datetime.utcnow() > user.otp_expires_at:
        return False

    if user.otp != otp:
        return False

    user.is_phone_verified = True
    user.otp = None
    user.otp_expires_at = None
    db_session.commit()

    return True


def get_user_by_phone(phone: str):
    """Get user by phone number."""
    return db_session.exec(
        select(PhoneVerification).where(PhoneVerification.phone == phone)
    ).first()


def send_sms_via_sns(phone: str, message: str):
    """Send SMS via AWS SNS."""
    sns_client = boto3.client(
        "sns",
        region_name=os.environ.get("AWS_REGION", "us-east-1"),
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
    )

    try:
        response = sns_client.publish(
            PhoneNumber=phone,
            Message=message,
            MessageAttributes={
                'AWS.SNS.SMS.SMSType': {
                    'DataType': 'String',
                    'StringValue': 'Transactional',
                }
            },
        )
        print(f"SMS sent successfully. Message ID: {response['MessageId']}")
        return response
    except ClientError as e:
        print(f"Error sending SMS: {e.response['Error']['Message']}")
        raise e
