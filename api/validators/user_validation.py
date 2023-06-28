from uuid import UUID

from pydantic import BaseModel


class RegistrationPayload(BaseModel):
    name: str
    email: str
    address: str
    entity_type: str
    username: str
    password: str


class RegistrationResponse(BaseModel):
    id: UUID


class FirebaseRegistrationPayload(BaseModel):
    email: str
    password: str


class FirebaseRegistrationResponse(BaseModel):
    user_id: str


class LoginPayload(BaseModel):
    email: str
    password: str


class LoginResponse(BaseModel):
    token: str


class FirebaseLoginPayload(BaseModel):
    email: str
    password: str


class FirebaseLoginResponse(BaseModel):
    token: str


class ChangePasswordPayload(BaseModel):
    username: str
    old_password: str
    new_password: str


class ChangePasswordResponse(BaseModel):
    status: str


class LogoutResponse(BaseModel):
    status: str
