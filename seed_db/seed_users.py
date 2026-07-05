"""Seed script: inserts test users (with their PhoneVerification rows) into the DB."""

import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlmodel import Session, select
from models.db import engine
from models.entity.phone_verification import PhoneVerification
from models.entity.user_entity import User
from api.helpers.auth_helper import hash_password

USERS = [
    {
        "phone": "1234567890",
        "name": "Alice Tester",
        "email": "alice@example.com",
        "location": "New York, NY",
        "entity_type": "user",
    },
    {
        "phone": "1234567891",
        "name": "Bob Tester",
        "email": "bob@example.com",
        "location": "Austin, TX",
        "entity_type": "store",
    },
]


def seed():
    plain_password = os.environ.get("SEED_PASSWORD")
    if not plain_password:
        raise RuntimeError("SEED_PASSWORD env var is not set. Add it to .env.")

    hashed = hash_password(plain_password)

    with Session(engine) as session:
        inserted = 0
        skipped = 0
        for data in USERS:
            # Phone is the login key, so it decides whether the user exists.
            existing = session.exec(
                select(PhoneVerification).where(PhoneVerification.phone == data["phone"])
            ).first()
            if existing:
                print(f"  ~ skipping (already exists): {data['name']} ({data['phone']})")
                skipped += 1
                continue

            phone_verification = PhoneVerification(
                id=uuid.uuid4(),
                phone=data["phone"],
                entity_type=data["entity_type"],
                password=hashed,
                is_phone_verified=True,
            )
            session.add(phone_verification)
            session.flush()

            user = User(
                name=data["name"],
                email=data["email"],
                entity_id=phone_verification.id,
                location=data["location"],
                is_active=True,
            )
            session.add(user)
            print(f"  + user: {user.name} ({user.email})")
            inserted += 1

        session.commit()
        print(f"\nDone — inserted {inserted} users, skipped {skipped}.")


if __name__ == "__main__":
    seed()
