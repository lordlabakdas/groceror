from uuid import UUID
from typing import Optional, Union

from pydantic import BaseModel

from models.entity.user_entity import UserType


class RegistrationPayload(BaseModel):
    #name: str
    #email: Optional[str] = None
    phone: str
    entity_type: UserType
    password: str


class RegistrationResponse(BaseModel):
    id: UUID


class SendOTPPayload(BaseModel):
    phone: str


class SendOTPResponse(BaseModel):
    message: str


class VerifyOTPPayload(BaseModel):
    phone: str
    otp: str


class VerifyOTPResponse(BaseModel):
    message: str


class UserProfilePayload(BaseModel):
    name: str
    email: str
    location: Optional[str] = None


class StoreProfilePayload(BaseModel):
    name: str
    email: str
    website: str
    location: Optional[str] = None


class ProfilePayload(BaseModel):
    name: str
    email: str
    location: Optional[str] = None
    website: Optional[str] = None  # Only for store users


class ProfileResponse(BaseModel):
    message: str


class FirebaseRegistrationPayload(BaseModel):
    email: str
    password: str


class FirebaseRegistrationResponse(BaseModel):
    user_id: str


class LoginPayload(BaseModel):
    phone: str
    password: str


class LoginResponse(BaseModel):
    token: str


class FirebaseLoginPayload(BaseModel):
    email: str
    password: str


class FirebaseLoginResponse(BaseModel):
    token: str


class ChangePasswordPayload(BaseModel):
    new_password: str


class ChangePasswordResponse(BaseModel):
    status: str


class LogoutResponse(BaseModel):
    status: str
