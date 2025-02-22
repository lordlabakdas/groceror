import logging
from typing import Dict, Union

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from config import JWTConfig
from models.service.user_service import UserService

logger = logging.getLogger()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


async def auth_required(token: str = Depends(oauth2_scheme)):
    try:
        jwt_obj = JWT()
        payload = jwt_obj.decode_token(token=token)
        email: str = payload.get("sub")
    except Exception as e:
        logger.exception(f"Invalid authentication credentials {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
        )
    else:
        user_service_obj = UserService()
        existing_user = user_service_obj.get_user_by_email(email=email)
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

    def create_token(self, payload: str) -> Dict:
        return jwt.encode(
            payload=payload, key=self.secret_key, algorithm=self.algorithm
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
