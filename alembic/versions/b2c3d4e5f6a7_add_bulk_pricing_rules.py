"""add bulk pricing rules

Revision ID: a1b2c3d4e5f6
Revises: f6a7b8c9d0e1
Create Date: 2026-07-05

"""
from alembic import op

revision = "b2c3d4e5f6a7"
down_revision = "f6a7b8c9d0e1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS bulkrule (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            store_id            UUID NOT NULL REFERENCES store(id) ON DELETE CASCADE,
            name                VARCHAR NOT NULL,
            rule_type           VARCHAR NOT NULL CHECK (rule_type IN ('bxgf', 'bundle')),
            is_active           BOOLEAN NOT NULL DEFAULT TRUE,
            bxgf_inventory_id   UUID REFERENCES inventory(id) ON DELETE SET NULL,
            buy_quantity        INTEGER,
            free_quantity       INTEGER,
            discount_type       VARCHAR CHECK (discount_type IN ('percent', 'fixed')),
            discount_value      DOUBLE PRECISION,
            created_at          TIMESTAMP NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_bulkrule_store_id ON bulkrule(store_id)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS bulkruleitem (
            id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            rule_id      UUID NOT NULL REFERENCES bulkrule(id) ON DELETE CASCADE,
            inventory_id UUID NOT NULL REFERENCES inventory(id) ON DELETE CASCADE
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_bulkruleitem_rule_id ON bulkruleitem(rule_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS bulkruleitem")
    op.execute("DROP TABLE IF EXISTS bulkrule")
