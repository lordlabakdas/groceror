from uuid import UUID

from pydantic import BaseModel


class RegistrationPayload(BaseModel):
    username: str


class RegistrationResponse(BaseModel):
    id: UUID
