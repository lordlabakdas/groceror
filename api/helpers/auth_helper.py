from google.auth.transport import requests
from google.oauth2 import id_token

from models.db import db_session
from models.entity.user_entity import User


def validate_google_token(token, client_id):
    try:
        idinfo = id_token.verify_oauth2_token(token, requests.Request(), client_id)

        if "email" not in idinfo:
            raise ValueError("Email not present in token")

        return idinfo

    except ValueError as e:
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
        password=password,
    )
    db_session.add(user)
    db_session.commit()
    return user


def get_user_by_email(email: str):
    user = db.session.query(User).filter(User.email == email).first()
    return user


def get_user_by_id(user_id: str):
    user = db.session.query(User).filter(User.id == user_id).first()
    return user


def get_user_by_username(username: str):
    user = db.session.query(User).filter(User.username == username).first()
    return user
