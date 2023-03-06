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


class LoginPayload(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    id: UUID


class ChangePasswordPayload(BaseModel):
    username: str
    old_password: str
    new_password: str


class ChangePasswordResponse(BaseModel):
    status: str


class LogoutResponse(BaseModel):
    status: str
