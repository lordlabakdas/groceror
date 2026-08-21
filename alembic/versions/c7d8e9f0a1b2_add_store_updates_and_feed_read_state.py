"""add store feed posts and feed read state

Revision ID: c7d8e9f0a1b2
Revises: b3c4d5e6f7a8
Create Date: 2026-08-21

"""
from alembic import op

revision = "c7d8e9f0a1b2"
down_revision = "b3c4d5e6f7a8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS storefeedpost (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            store_id    UUID NOT NULL REFERENCES store(id) ON DELETE CASCADE,
            update_type VARCHAR NOT NULL,
            message     VARCHAR NOT NULL,
            ref_id      UUID,
            created_at  TIMESTAMP NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_storefeedpost_store_id ON storefeedpost(store_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_storefeedpost_created_at ON storefeedpost(created_at)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS feedreadstate (
            id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id       UUID NOT NULL UNIQUE REFERENCES "user"(id) ON DELETE CASCADE,
            last_read_at  TIMESTAMP NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_feedreadstate_user_id ON feedreadstate(user_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS feedreadstate")
    op.execute("DROP TABLE IF EXISTS storefeedpost")
