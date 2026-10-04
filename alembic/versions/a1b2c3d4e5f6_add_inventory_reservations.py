"""add inventory reservations

Revision ID: c4d5e6f7a8b9
Revises: b3c4d5e6f7a8
"""
from alembic import op

revision = "c4d5e6f7a8b9"
down_revision = "b3c4d5e6f7a8"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS inventoryreservation (
            id UUID PRIMARY KEY,
            user_id UUID NOT NULL REFERENCES \"user\"(id),
            cart_id UUID NOT NULL REFERENCES cartentity(id),
            inventory_id UUID NOT NULL REFERENCES inventory(id),
            quantity INTEGER NOT NULL CHECK (quantity > 0),
            status VARCHAR(20) NOT NULL DEFAULT 'active',
            expires_at TIMESTAMP NOT NULL,
            created_at TIMESTAMP NOT NULL,
            updated_at TIMESTAMP NOT NULL,
            CONSTRAINT inventoryreservation_status_check CHECK (status IN ('active', 'expired', 'consumed', 'released'))
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_inventoryreservation_user_id ON inventoryreservation(user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_inventoryreservation_cart_id ON inventoryreservation(cart_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_inventoryreservation_inventory_id ON inventoryreservation(inventory_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_inventoryreservation_status ON inventoryreservation(status)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_inventoryreservation_expires_at ON inventoryreservation(expires_at)")


def downgrade():
    op.execute("DROP TABLE IF EXISTS inventoryreservation")
