import os

import boto3
from botocore.exceptions import ClientError
from firebase_admin import auth as firebase_auth
from google.auth.transport import requests
from google.oauth2 import id_token
from passlib.context import CryptContext

from api.validators.user_validation import ChangePasswordPayload
from models.db import db_session
from models.entity.user_entity import User


def validate_google_token(token, client_id):
    try:
        idinfo = id_token.verify_oauth2_token(token, requests.Request(), client_id)

        if "email" not in idinfo:
            raise ValueError("Email not present in token")

        return idinfo

    except ValueError:
        # Invalid token
        return None


def register(
    name: str, email: str, address: str, entity_type: str, password: str
):
    user = User(
        name=name,
        email=email,
        address=address,
        entity_type=entity_type,
        password=hash_password(password),
    )
    db_session.add(user)
    db_session.commit()
    return user


def get_user_by_email(email: str):
    user = db_session.query(User).filter(User.email == email).first()
    return user


def get_user_by_id(user_id: str):
    user = db_session.query(User).filter(User.id == user_id).first()
    return user


def get_user_by_username(username: str):
    user = db_session.query(User).filter(User.username == username).first()
    return user


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def is_user_exists(email: str) -> bool:
    user = get_user_by_email(email)
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


def send_verification_email(email: str, token: str):
    # Create a new SES resource
    ses_client = boto3.client(
        "ses", region_name=os.environ.get("AWS_REGION", "us-east-2")
    )

    # The subject line for the email.
    subject = "Verify your email address"

    # The email body for recipients with non-HTML email clients.
    body_text = f"Please click the following link to verify your email: {os.environ['BASE_URL']}/verify/{token}"

    # The HTML body of the email.
    body_html = f"""<html>
    <head></head>
    <body>
        <h1>Verify your email address</h1>
        <p>Please click the following link to verify your email:</p>
        <p><a href="{os.environ["BASE_URL"]}/verify/{token}">Verify Email</a></p>
    </body>
    </html>
    """

    try:
        response = ses_client.send_email(
            Destination={
                "ToAddresses": [email],
            },
            Message={
                "Body": {
                    "Html": {
                        "Charset": "UTF-8",
                        "Data": body_html,
                    },
                    "Text": {
                        "Charset": "UTF-8",
                        "Data": body_text,
                    },
                },
                "Subject": {
                    "Charset": "UTF-8",
                    "Data": subject,
                },
            },
            Source=os.environ.get("SES_SENDER_EMAIL"),
        )
    except ClientError as e:
        print(f"An error occurred: {e.response['Error']['Message']}")
    else:
        print(f"Email sent! Message ID: {response['MessageId']}")
