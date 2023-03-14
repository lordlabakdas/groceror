import logging
import uuid
from typing import Dict

import bcrypt
import sqlalchemy

from helpers.exceptions import GrocerorError
from helpers.jwt import JWT
from models.db import db_session
from models.entity.user_entity import User

logger = logging.getLogger()


class UserServiceError(GrocerorError):
    def __init__(
        self, entity: str = "user", action: str = None, message: str = None
    ) -> None:
        super().__init__(entity, action, message)


class UserService(object):
    def register(self, registration_payload) -> uuid.uuid4:
        registration_payload["password"] = bcrypt.hashpw(
            registration_payload["password"].encode("utf-8"), bcrypt.gensalt()
        )
        try:
            new_user_obj = User(**registration_payload)
            db_session.add(new_user_obj)
            db_session.commit()
            db_session.refresh()
        except (sqlalchemy.exc.IntegrityError, sqlalchemy.exc.DataError):
            logger.exception(
                f"Exception seen when registering user {str(registration_payload)} to database"
            )
            raise UserServiceError(
                action="registration",
                message=f"Exception seen when registering user {str(registration_payload)} to database",
            )
        else:
            return new_user_obj.id
        finally:
            db_session.close()

    def login(self, login_payload) -> Dict[str]:
        try:
            user_obj = (
                db_session.query(User).filter_by(email=login_payload["email"]).first()
            )
        except Exception:
            logger.exception(
                f"Exception seen when logging in user {str(login_payload)} to database"
            )
            raise UserServiceError(
                action="login",
                message=f"Exception seen when registering user {str(login_payload)} to database",
            )
        else:
            if bcrypt.checkpw(
                login_payload["password"].encode("utf-8"), user_obj.password
            ):
                jwt_obj = JWT()
                token = jwt_obj.create_token(
                    payload={"id": user_obj.id, "email": user_obj.email}
                )
                return {"access_token": token}
            else:
                logger.critical(
                    f"Passwords do not match for user {login_payload['email']}"
                )
                raise UserServiceError(
                    action="login",
                    message=f"Passwords do not match for user {login_payload['email']}",
                )
        finally:
            db_session.close()

    def get_user_by_email(self, email: str) -> User:
        user_obj = db_session.query(User).filter_by(email=email).first()
        return user_obj
