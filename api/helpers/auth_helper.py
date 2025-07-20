import os
import random
import string
from datetime import datetime, timedelta

import boto3
from botocore.exceptions import ClientError
from firebase_admin import auth as firebase_auth
from google.auth.transport import requests
from google.oauth2 import id_token
from passlib.context import CryptContext

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
        # Invalid token
        return None


def register(register_payload: dict):
    # Check if phone is verified
    user_by_phone = get_user_by_phone(register_payload["phone"])
    if not user_by_phone:
        raise ValueError("User not found")
        # Check if phone is verified through OTP
    if not user_by_phone.is_phone_verified:
        raise ValueError("Phone number not verified")
    
    # Update the existing user record with registration data
    user = user_by_phone
    user.entity_type = register_payload["entity_type"].value
    user.password = hash_password(register_payload["password"])
    
    db_session.commit()
    return user


def get_user_by_email(email: str):
    user = db_session.query(User).filter(User.email == email).first()
    return user


def get_user_by_id(user_id: str):
    user = db_session.query(User).filter(User.id == user_id).first()
    return user


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def is_user_exists(phone: str) -> bool:
    user = get_user_by_phone(phone)
    return user is not None


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
    """Set user profile for regular users"""
    # Check if user profile already exists
    user = db_session.query(User).filter(User.entity_id == entity.id).first()
    
    if user:
        # Update existing user profile
        user.name = profile_payload.name
        user.email = profile_payload.email
        user.location = profile_payload.location
        user.updated_at = datetime.utcnow()
    else:
        # Create new user profile
        user = User(
            name=profile_payload.name,
            email=profile_payload.email,
            location=profile_payload.location,
            entity_id=entity.id,  # type: ignore
            is_active=True
        )
        db_session.add(user)
    
    db_session.commit()
    return user


def set_store_profile(entity: PhoneVerification, profile_payload: StoreProfilePayload):
    """Set store profile for store users"""
    # Check if store profile already exists
    store = db_session.query(Store).filter(Store.entity_id == entity.id).first()
    
    if store:
        # Update existing store profile
        store.name = profile_payload.name
        store.email = profile_payload.email
        store.website = profile_payload.website
        store.location = profile_payload.location
        store.updated_at = datetime.utcnow()
    else:
        # Create new store profile
        store = Store(
            name=profile_payload.name,
            email=profile_payload.email,
            website=profile_payload.website,
            location=profile_payload.location,
            entity_id=entity.id,  # type: ignore
            is_active=True
        )
        db_session.add(store)
    
    db_session.commit()
    return store


def set_profile(entity: PhoneVerification, profile_payload: ProfilePayload):
    """Set profile based on entity type"""
    if entity.entity_type == "store":
        # Convert to StoreProfilePayload
        store_payload = StoreProfilePayload(
            name=profile_payload.name,
            email=profile_payload.email,
            website=profile_payload.website or "",  # Required for store
            location=profile_payload.location
        )
        return set_store_profile(entity, store_payload)
    else:
        # Convert to UserProfilePayload
        user_payload = UserProfilePayload(
            name=profile_payload.name,
            email=profile_payload.email,
            location=profile_payload.location
        )
        return set_user_profile(entity, user_payload)


# def send_verification_email(email: str, token: str):
#     # Create a new SES resource
#     ses_client = boto3.client(
#         "ses", region_name=os.environ.get("AWS_REGION", "us-east-2")
#     )

#     # The subject line for the email.
#     subject = "Verify your email address"

#     # The email body for recipients with non-HTML email clients.
#     body_text = f"Please click the following link to verify your email: {os.environ['BASE_URL']}/verify/{token}"

#     # The HTML body of the email.
#     body_html = f"""<html>
#     <head></head>
#     <body>
#         <h1>Verify your email address</h1>
#         <p>Please click the following link to verify your email:</p>
#         <p><a href="{os.environ["BASE_URL"]}/verify/{token}">Verify Email</a></p>
#     </body>
#     </html>
#     """

#     try:
#         response = ses_client.send_email(
#             Destination={
#                 "ToAddresses": [email],
#             },
#             Message={
#                 "Body": {
#                     "Html": {
#                         "Charset": "UTF-8",
#                         "Data": body_html,
#                     },
#                     "Text": {
#                         "Charset": "UTF-8",
#                         "Data": body_text,
#                     },
#                 },
#                 "Subject": {
#                     "Charset": "UTF-8",
#                     "Data": subject,
#                 },
#             },
#             Source=os.environ.get("SES_SENDER_EMAIL"),
#         )
#     except ClientError as e:
#         print(f"An error occurred: {e.response['Error']['Message']}")
#     else:
#         print(f"Email sent! Message ID: {response['MessageId']}")


def generate_otp(length: int = 6) -> str:
    """Generate a random OTP of specified length"""
    return ''.join(random.choices(string.digits, k=length))


def send_otp(phone: str) -> str:
    """Generate and send OTP to the given phone number"""
    # Generate a 6-digit OTP
    otp = generate_otp(6)
    
    # Set expiration time (10 minutes from now)
    expires_at = datetime.utcnow() + timedelta(minutes=10)
    
    # Check if user already exists with this phone
    user = db_session.query(PhoneVerification).filter(PhoneVerification.phone == phone).first()
    
    if user:
        # Update existing user's OTP
        user.otp = otp
        user.otp_expires_at = expires_at
        user.is_phone_verified = False
    else:
        # Create a temporary user record for OTP verification
        user = PhoneVerification(
            phone=phone,
            otp=otp,
            otp_expires_at=expires_at,
            is_phone_verified=False,
            # Set temporary values for required field
            password="",
            entity_type="user"  # Use string instead of UserType enum
        )
        db_session.add(user)
    
    db_session.commit()
    
    # Send OTP via AWS SNS
    # try:
    #     send_sms_via_sns(phone, f"Your OTP is: {otp}. Valid for 10 minutes.")
    # except Exception as e:
    #     print(f"Failed to send SMS via SNS: {e}")
        # Fallback to console output for development
    print(f"OTP for {phone}: {otp}")
    
    return otp


def verify_otp(phone: str, otp: str) -> bool:
    """Verify OTP for the given phone number"""
    user = db_session.query(PhoneVerification).filter(PhoneVerification.phone == phone).first()
    
    if not user or not user.otp:
        return False
    
    # Check if OTP has expired
    if user.otp_expires_at and datetime.utcnow() > user.otp_expires_at:
        return False
    
    # Check if OTP matches
    if user.otp != otp:
        return False
    
    # Mark phone as verified
    user.is_phone_verified = True
    user.otp = None
    user.otp_expires_at = None
    db_session.commit()
    
    return True


def get_user_by_phone(phone: str):
    """Get user by phone number"""
    user = db_session.query(PhoneVerification).filter(PhoneVerification.phone == phone).first()
    return user


def send_sms_via_sns(phone: str, message: str):
    """Send SMS via AWS SNS"""
    # Create SNS client
    sns_client = boto3.client(
        "sns",
        region_name=os.environ.get("AWS_REGION", "us-east-1"),
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY")
    )
    
    try:
        # Send SMS
        response = sns_client.publish(
            PhoneNumber=phone,
            Message=message,
            MessageAttributes={
                'AWS.SNS.SMS.SMSType': {
                    'DataType': 'String',
                    'StringValue': 'Transactional'
                }
            }
        )
        
        print(f"SMS sent successfully. Message ID: {response['MessageId']}")
        return response
        
    except ClientError as e:
        print(f"Error sending SMS: {e.response['Error']['Message']}")
        raise e
