"""add saved deals

Revision ID: d1e2f3a4b5c6
Revises: c7d8e9f0a1b2
Create Date: 2026-08-22

"""
from alembic import op

revision = "d1e2f3a4b5c6"
down_revision = "c7d8e9f0a1b2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS saveddeal (
            id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id       UUID NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
            feed_post_id  UUID NOT NULL REFERENCES storefeedpost(id) ON DELETE CASCADE,
            created_at    TIMESTAMP NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_saveddeal_user_feedpost UNIQUE (user_id, feed_post_id)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_saveddeal_user_id ON saveddeal(user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_saveddeal_feed_post_id ON saveddeal(feed_post_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS saveddeal")
