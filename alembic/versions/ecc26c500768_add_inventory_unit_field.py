"""add inventory unit field

Revision ID: ecc26c500768
Revises: 0299fe7a78b5
Create Date: 2026-08-17 22:07:32.162786

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


revision: str = 'ecc26c500768'
down_revision: Union[str, None] = '0299fe7a78b5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE inventoryunit AS ENUM ('UNIT', 'G', 'KG');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)
    op.execute(
        "ALTER TABLE inventory ADD COLUMN IF NOT EXISTS unit inventoryunit NOT NULL DEFAULT 'UNIT'"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE inventory DROP COLUMN IF EXISTS unit")
    op.execute("DROP TYPE IF EXISTS inventoryunit")
