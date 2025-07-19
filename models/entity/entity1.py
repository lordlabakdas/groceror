from datetime import datetime
from typing import Optional
import uuid
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


class Entity1(Base):
    __tablename__ = "entity1"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    phone = Column(String(20), nullable=False, default="")
    entity_type = Column(String(20), nullable=True)
    password = Column(Text, nullable=False)
    is_phone_verified = Column(Boolean, default=False)
    otp = Column(String(10), nullable=True)
    otp_expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)