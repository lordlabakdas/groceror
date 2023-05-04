import logging

from fastapi import APIRouter, HTTPException
from google.oauth2 import id_token


logger = logging.getLogger("groceror")
google_login_apis = APIRouter()


@google_login_apis.post("/login")
async def google_login(token: str):
    try:
        # Verify token and return user ID
        id_info = id_token.verify_oauth2_token(token, None)
    except ValueError:
        # Invalid token
        raise HTTPException(status_code=400, detail="Invalid Google token")
    else:
        return {"message": f"Logged in with Google as {id_info['email']}"}
