import uuid

from models.entity.userentity import User


class UserService(object):
    def register(self, registration_payload):
        User(**registration_payload).save()

    def login(self, login_payload):
        return uuid.uuid4()
