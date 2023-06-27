from google.auth.transport import requests
from google.oauth2 import id_token

from models.db import db_session
from models.entity.user_entity import User
from passlib.context import CryptContext
from firebase_admin import auth as firebase_auth


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
    name: str, email: str, address: str, entity_type: str, username: str, password: str
):
    user = User(
        name=name,
        email=email,
        address=address,
        entity_type=entity_type,
        username=username,
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
