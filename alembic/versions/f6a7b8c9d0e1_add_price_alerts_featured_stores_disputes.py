"""add price alerts, featured stores, disputes

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-07-05

"""
from alembic import op

revision = "f6a7b8c9d0e1"
down_revision = "e5f6a7b8c9d0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -- pricealert --
    op.execute("""
        CREATE TABLE IF NOT EXISTS pricealert (
            id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id       UUID NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
            inventory_id  UUID NOT NULL REFERENCES inventory(id) ON DELETE CASCADE,
            target_price  DOUBLE PRECISION NOT NULL,
            is_active     BOOLEAN NOT NULL DEFAULT TRUE,
            is_triggered  BOOLEAN NOT NULL DEFAULT FALSE,
            triggered_at  TIMESTAMP,
            created_at    TIMESTAMP NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_pricealert_user_id ON pricealert(user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_pricealert_inventory_id ON pricealert(inventory_id)")

    # -- featuredstore --
    op.execute("""
        CREATE TABLE IF NOT EXISTS featuredstore (
            id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            store_id   UUID NOT NULL UNIQUE REFERENCES store(id) ON DELETE CASCADE,
            tagline    TEXT,
            priority   INTEGER NOT NULL DEFAULT 0,
            start_date DATE,
            end_date   DATE,
            is_active  BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_featuredstore_store_id ON featuredstore(store_id)")

    # -- dispute --
    op.execute("""
        CREATE TABLE IF NOT EXISTS dispute (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            order_id    UUID NOT NULL REFERENCES "order"(id) ON DELETE CASCADE,
            user_id     UUID NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
            store_id    UUID NOT NULL REFERENCES store(id) ON DELETE CASCADE,
            reason      VARCHAR NOT NULL,
            description TEXT NOT NULL,
            status      VARCHAR NOT NULL DEFAULT 'open'
                        CHECK (status IN ('open','store_responded','resolved','closed')),
            resolution  VARCHAR CHECK (resolution IN ('refund','replacement','rejected','no_action')),
            created_at  TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at  TIMESTAMP NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_dispute_order_id ON dispute(order_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_dispute_user_id ON dispute(user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_dispute_store_id ON dispute(store_id)")

    # -- disputemessage --
    op.execute("""
        CREATE TABLE IF NOT EXISTS disputemessage (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            dispute_id  UUID NOT NULL REFERENCES dispute(id) ON DELETE CASCADE,
            sender_type VARCHAR NOT NULL CHECK (sender_type IN ('shopper','store')),
            message     TEXT NOT NULL,
            created_at  TIMESTAMP NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_disputemessage_dispute_id ON disputemessage(dispute_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS disputemessage")
    op.execute("DROP TABLE IF EXISTS dispute")
    op.execute("DROP TABLE IF EXISTS featuredstore")
    op.execute("DROP TABLE IF EXISTS pricealert")
