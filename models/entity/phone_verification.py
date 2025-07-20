from datetime import datetime
from typing import Optional
import uuid
from sqlmodel import SQLModel, Field


class PhoneVerification(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    phone: str = ""
    entity_type: Optional[str] = None
    password: str
    is_phone_verified: bool = Field(default=False)
    otp: Optional[str] = None
    otp_expires_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)
    updated_at: datetime = Field(default_factory=datetime.utcnow, nullable=False) 