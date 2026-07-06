"""add flash sales, back-in-stock alerts, store is_verified

Revision ID: f6b8d0e2a4c6
Revises: e5f7a9b1c3d5
Create Date: 2026-07-05

"""
from alembic import op

revision = "f6b8d0e2a4c6"
down_revision = "e5f7a9b1c3d5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # flashsale
    op.execute("""
        CREATE TABLE IF NOT EXISTS flashsale (
            id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            inventory_id UUID NOT NULL REFERENCES inventory(id) ON DELETE CASCADE,
            store_id     UUID NOT NULL REFERENCES store(id) ON DELETE CASCADE,
            sale_price   FLOAT NOT NULL,
            start_at     TIMESTAMP NOT NULL,
            end_at       TIMESTAMP NOT NULL,
            is_active    BOOLEAN NOT NULL DEFAULT TRUE,
            created_at   TIMESTAMP NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_flashsale_inventory_id ON flashsale(inventory_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_flashsale_store_id ON flashsale(store_id)")

    # backinstockalert
    op.execute("""
        CREATE TABLE IF NOT EXISTS backinstockalert (
            id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id      UUID NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
            inventory_id UUID NOT NULL REFERENCES inventory(id) ON DELETE CASCADE,
            is_triggered BOOLEAN NOT NULL DEFAULT FALSE,
            triggered_at TIMESTAMP,
            created_at   TIMESTAMP NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_backinstockalert_user_item UNIQUE (user_id, inventory_id)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_backinstockalert_user_id ON backinstockalert(user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_backinstockalert_inventory_id ON backinstockalert(inventory_id)")

    # store.is_verified
    op.execute("ALTER TABLE store ADD COLUMN IF NOT EXISTS is_verified BOOLEAN NOT NULL DEFAULT FALSE")


def downgrade() -> None:
    op.execute("ALTER TABLE store DROP COLUMN IF EXISTS is_verified")
    op.execute("DROP TABLE IF EXISTS backinstockalert")
    op.execute("DROP TABLE IF EXISTS flashsale")
