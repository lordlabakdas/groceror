"""add wishlists, product reviews, scheduled orders

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-07-05

"""
from alembic import op

revision = "c3d4e5f6a7b8"
down_revision = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # wishlistitem
    op.execute("""
        CREATE TABLE IF NOT EXISTS wishlistitem (
            id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id      UUID NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
            inventory_id UUID NOT NULL REFERENCES inventory(id) ON DELETE CASCADE,
            created_at   TIMESTAMP NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_wishlist_user_item UNIQUE (user_id, inventory_id)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_wishlistitem_user_id ON wishlistitem(user_id)")

    # productreview
    op.execute("""
        CREATE TABLE IF NOT EXISTS productreview (
            id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id      UUID NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
            inventory_id UUID NOT NULL REFERENCES inventory(id) ON DELETE CASCADE,
            store_id     UUID NOT NULL REFERENCES store(id) ON DELETE CASCADE,
            rating       SMALLINT NOT NULL CHECK (rating BETWEEN 1 AND 5),
            comment      TEXT,
            created_at   TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at   TIMESTAMP NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_product_review_user_item UNIQUE (user_id, inventory_id)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_productreview_inventory_id ON productreview(inventory_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_productreview_user_id ON productreview(user_id)")

    # scheduledorder
    op.execute("""
        CREATE TABLE IF NOT EXISTS scheduledorder (
            id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id        UUID NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
            store_id       UUID NOT NULL REFERENCES store(id) ON DELETE CASCADE,
            store_name     VARCHAR NOT NULL,
            frequency      VARCHAR NOT NULL CHECK (frequency IN ('weekly','biweekly','monthly')),
            next_run_date  DATE NOT NULL,
            is_active      BOOLEAN NOT NULL DEFAULT TRUE,
            last_run_at    TIMESTAMP,
            created_at     TIMESTAMP NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_scheduledorder_user_id ON scheduledorder(user_id)")

    # scheduledorderitem
    op.execute("""
        CREATE TABLE IF NOT EXISTS scheduledorderitem (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            scheduled_order_id  UUID NOT NULL REFERENCES scheduledorder(id) ON DELETE CASCADE,
            inventory_id        UUID NOT NULL REFERENCES inventory(id) ON DELETE CASCADE,
            quantity            INTEGER NOT NULL DEFAULT 1,
            item_name           VARCHAR NOT NULL
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_scheduledorderitem_scheduled_order_id ON scheduledorderitem(scheduled_order_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS scheduledorderitem")
    op.execute("DROP TABLE IF EXISTS scheduledorder")
    op.execute("DROP TABLE IF EXISTS productreview")
    op.execute("DROP TABLE IF EXISTS wishlistitem")
