import logging
from datetime import datetime, timedelta
from typing import Dict, Union

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from api.helpers import auth_helper
from config import JWTConfig
from models.service.user_service import UserService

logger = logging.getLogger()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


async def auth_required(token: str = Depends(oauth2_scheme)):
    try:
        jwt_obj = JWT()
        decoded_token = jwt_obj.decode_token(token=token)
        phone = decoded_token.get("sub")
        if not phone:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication credentials",
            )
    except Exception as e:
        logger.exception(f"Invalid authentication credentials {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
        )
    else:
        existing_user = auth_helper.get_user_by_phone(phone=phone)
        if existing_user:
            return existing_user
        else:
            logger.exception("Invalid authentication credentials {e}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication credentials",
            )


class JWT(object):
    def __init__(self) -> None:
        self.algorithm = JWTConfig.JWT_ALGORITHM
        self.secret_key = JWTConfig.JWT_SECRET_KEY
        self.expiration_hours = 24  # Token expires in 24 hours

    def create_token(self, payload: dict) -> str:
        # Add standard JWT claims
        now = datetime.utcnow()
        token_payload = {
            **payload,
            "iat": now,  # Issued at
            "exp": now + timedelta(hours=self.expiration_hours),  # Expiration
            "nbf": now,  # Not valid before
            "jti": f"{payload.get('sub', '')}_{now.timestamp()}"  # Unique token ID
        }
        return jwt.encode(
            payload=token_payload, key=self.secret_key, algorithm=self.algorithm
        )

    def decode_token(self, token: str) -> Union[Dict[str, str], None]:
        try:
            decoded_token = jwt.decode(
                token, key=self.secret_key, algorithms=[self.algorithm]
            )
        except jwt.ExpiredSignatureError:
            logger.exception("Token has expired")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has expired"
            )
        except jwt.InvalidTokenError:
            logger.exception("Invalid token")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
            )
        except Exception as e:
            logger.exception(f"Error while decoding token: {e}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Error decoding token"
            )
        return decoded_token
