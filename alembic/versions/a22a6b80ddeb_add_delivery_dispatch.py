"""add delivery dispatch (Shiprocket Quick)

Revision ID: a22a6b80ddeb
Revises: ecc26c500768
Create Date: 2026-08-18

See SPEC_DELIVERY_DISPATCH.md for the design this implements.
"""

from alembic import op

revision = "a22a6b80ddeb"
down_revision = "ecc26c500768"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -- delivery --
    op.execute("""
        CREATE TABLE IF NOT EXISTS delivery (
            id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            order_id             UUID NOT NULL UNIQUE REFERENCES "order"(id) ON DELETE CASCADE,
            store_id             UUID NOT NULL REFERENCES store(id) ON DELETE CASCADE,
            vendor               VARCHAR NOT NULL DEFAULT 'shiprocket_quick',
            vendor_quote_id      VARCHAR,
            vendor_delivery_id   VARCHAR,
            status               VARCHAR NOT NULL DEFAULT 'quoted'
                                 CHECK (status IN ('quoted','requested','confirmed','picked_up',
                                                    'in_transit','delivered','failed','cancelled')),
            quoted_fee           DOUBLE PRECISION NOT NULL,
            rider_name           VARCHAR,
            rider_phone          VARCHAR,
            tracking_url         VARCHAR,
            requested_at         TIMESTAMP,
            delivered_at         TIMESTAMP,
            raw_webhook_payload  TEXT,
            created_at           TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at           TIMESTAMP NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_delivery_store_id ON delivery(store_id)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_delivery_vendor_delivery_id ON delivery(vendor_delivery_id)"
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_delivery_status ON delivery(status)")

    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("ALTER TABLE delivery ENABLE ROW LEVEL SECURITY")

    # -- order: new nullable delivery-related columns --
    op.execute(
        'ALTER TABLE "order" ADD COLUMN IF NOT EXISTS delivery_fee DOUBLE PRECISION'
    )
    op.execute(
        'ALTER TABLE "order" ADD COLUMN IF NOT EXISTS delivery_address_line VARCHAR'
    )
    op.execute(
        'ALTER TABLE "order" ADD COLUMN IF NOT EXISTS delivery_lat DOUBLE PRECISION'
    )
    op.execute(
        'ALTER TABLE "order" ADD COLUMN IF NOT EXISTS delivery_lng DOUBLE PRECISION'
    )


def downgrade() -> None:
    op.execute('ALTER TABLE "order" DROP COLUMN IF EXISTS delivery_lng')
    op.execute('ALTER TABLE "order" DROP COLUMN IF EXISTS delivery_lat')
    op.execute('ALTER TABLE "order" DROP COLUMN IF EXISTS delivery_address_line')
    op.execute('ALTER TABLE "order" DROP COLUMN IF EXISTS delivery_fee')
    op.execute("DROP TABLE IF EXISTS delivery")
