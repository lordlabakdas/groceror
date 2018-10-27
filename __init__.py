from data_models.db import db


class User(db.Model):
    __tablename__ = "user"
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), nullable=False)
    name = db.Column(db.String, nullable=False)
    password = db.Column(db.String, nullable=False)
    otp = db.Column(db.Integer, nullable=True)
    location = db.Column(db.String, nullable=True)
    phone = db.Column(db.String)
    prev_password = db.Column(db.String)
