"""add store follow and low-stock alert fields

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-07-05

"""
from alembic import op

revision = "e5f7a9b1c3d5"
down_revision = "c3d4e5f6a7b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # storefollow
    op.execute("""
        CREATE TABLE IF NOT EXISTS storefollow (
            id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id    UUID NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
            store_id   UUID NOT NULL REFERENCES store(id) ON DELETE CASCADE,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_storefollow_user_store UNIQUE (user_id, store_id)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_storefollow_user_id ON storefollow(user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_storefollow_store_id ON storefollow(store_id)")

    # add triggered fields to stockthreshold
    op.execute("ALTER TABLE stockthreshold ADD COLUMN IF NOT EXISTS is_triggered BOOLEAN NOT NULL DEFAULT FALSE")
    op.execute("ALTER TABLE stockthreshold ADD COLUMN IF NOT EXISTS triggered_at TIMESTAMP")
    op.execute("ALTER TABLE stockthreshold ADD COLUMN IF NOT EXISTS acknowledged_at TIMESTAMP")


def downgrade() -> None:
    op.execute("ALTER TABLE stockthreshold DROP COLUMN IF EXISTS is_triggered")
    op.execute("ALTER TABLE stockthreshold DROP COLUMN IF EXISTS triggered_at")
    op.execute("ALTER TABLE stockthreshold DROP COLUMN IF EXISTS acknowledged_at")
    op.execute("DROP TABLE IF EXISTS storefollow")
