from google.oauth2 import id_token
from google.auth.transport import requests


def validate_google_token(token, client_id):
    try:
        idinfo = id_token.verify_oauth2_token(token, requests.Request(), client_id)

        if "email" not in idinfo:
            raise ValueError("Email not present in token")

        return idinfo

    except ValueError as e:
        # Invalid token
        return None
