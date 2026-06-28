"""add product table

Revision ID: a1b2c3d4e5f6
Revises: 30c7e13a0ed6
Create Date: 2026-06-27 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '30c7e13a0ed6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE product (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name VARCHAR NOT NULL,
            category inventorycategory NOT NULL,
            image_url VARCHAR,
            default_price FLOAT NOT NULL DEFAULT 0.0,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_product_name UNIQUE (name)
        )
    """)
    op.execute("CREATE INDEX ix_product_name ON product (name)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_product_name")
    op.execute("DROP TABLE IF EXISTS product")
