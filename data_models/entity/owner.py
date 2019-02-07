from sqlalchemy import Column, Integer, String, ForeignKey
from data_models.db import Base


class Owner(Base):
    __tablename__ = 'owner'
    id = Column(Integer, primary_key=True)
    first_name = Column(String(80), nullable=False)
    last_name = Column(String(255), nullable=True)
    username = Column(String(80), nullable=False)
    email = Column(Integer, nullable=False)
    password = Column(String)
    phone = Column(String)
    prev_password = Column(String)
    store_id = Column(Integer, ForeignKey('store.id'))
    otp = Column(String)