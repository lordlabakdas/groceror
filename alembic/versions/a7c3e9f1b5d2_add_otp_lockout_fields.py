"""add otp_attempts and otp_locked_until to phoneverification

Revision ID: a7c3e9f1b5d2
Revises: d6e7f8a9b0c1
Create Date: 2026-10-17

"""
from alembic import op

revision = "a7c3e9f1b5d2"
down_revision = "d6e7f8a9b0c1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE phoneverification ADD COLUMN IF NOT EXISTS "
        "otp_attempts INTEGER NOT NULL DEFAULT 0"
    )
    op.execute(
        "ALTER TABLE phoneverification ADD COLUMN IF NOT EXISTS "
        "otp_locked_until TIMESTAMP"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE phoneverification DROP COLUMN IF EXISTS otp_locked_until")
    op.execute("ALTER TABLE phoneverification DROP COLUMN IF EXISTS otp_attempts")
