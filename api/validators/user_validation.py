from uuid import UUID

from pydantic import BaseModel

from models.entity.user_entity import UserType


class RegistrationPayload(BaseModel):
    #name: str
    #email: Optional[str] = None
    phone: str
    entity_type: UserType
    password: str


class RegistrationResponse(BaseModel):
    id: int


class SendOTPPayload(BaseModel):
    phone: str


class SendOTPResponse(BaseModel):
    message: str


class VerifyOTPPayload(BaseModel):
    phone: str
    otp: str


class VerifyOTPResponse(BaseModel):
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
    username: str
    old_password: str
    new_password: str


class ChangePasswordResponse(BaseModel):
    status: str


class LogoutResponse(BaseModel):
    status: str
