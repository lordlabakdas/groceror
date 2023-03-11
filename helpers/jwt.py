from typing import Dict, Union
import jwt
from config import JWTConfig


class JWT(object):
    def __init__(self) -> None:
        self.algorithm = JWTConfig.JWT_ALGORITHM
        self.secret_key = JWTConfig.JWT_SECRET_KEY

    def create_token(self, payload: str) -> Dict[str]:
        return jwt.encode(
            payload=payload, key=self.secret_key, algorithm=self.algorithm
        )

    def decode_token(self, token: str) -> Union[Dict[str, str], None]:
        try:
            decoded_token = jwt.decode(
                token, key=self.secret_key, algorithm=self.algorithm
            )
        except Exception:
            return None
        else:
            return decoded_token
