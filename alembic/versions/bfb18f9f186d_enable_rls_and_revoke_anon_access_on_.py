"""enable RLS and revoke anon access on all tables

Revision ID: bfb18f9f186d
Revises: a1b2c3d4e5f6
Create Date: 2026-06-28 12:07:21.736935

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


revision: str = 'bfb18f9f186d'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLES = [
    "alembic_version",
    "cartentity",
    "cartitementity",
    "inventory",
    "inventoryexpiry",
    '"order"',
    "orderitem",
    "phoneverification",
    "product",
    "stockthreshold",
    "store",
    '"user"',
]


def upgrade() -> None:
    op.execute("REVOKE ALL ON ALL TABLES IN SCHEMA public FROM anon, authenticated")
    for table in TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    for table in TABLES:
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
    op.execute("GRANT SELECT ON ALL TABLES IN SCHEMA public TO anon")
    op.execute("GRANT ALL ON ALL TABLES IN SCHEMA public TO authenticated")
