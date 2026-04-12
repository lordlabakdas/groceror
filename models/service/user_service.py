import logging
import uuid

import bcrypt
import sqlalchemy
from sqlmodel import select

from helpers.exceptions import GrocerorError
from models.db import db_session
from models.entity.user_entity import User

logger = logging.getLogger()


class UserServiceError(GrocerorError):
    def __init__(
        self, entity: str = "user", action: str = None, message: str = None
    ) -> None:
        super().__init__(entity, action, message)


class UserService(object):
    def register(self, registration_payload) -> uuid.UUID:
        registration_payload["password"] = bcrypt.hashpw(
            registration_payload["password"].encode("utf-8"), bcrypt.gensalt()
        )
        try:
            new_user_obj = User(**registration_payload)
            db_session.add(new_user_obj)
            db_session.commit()
            db_session.refresh(new_user_obj)
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
            db_session.remove()

    def get_user_by_email(self, email: str) -> User:
        return db_session.exec(select(User).where(User.email == email)).first()
