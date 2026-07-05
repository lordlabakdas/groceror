"""add platform features: coupons, delivery zones, loyalty, order discount fields

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-07-05

"""
from alembic import op

revision = "e5f6a7b8c9d0"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -- coupon table --
    op.execute("""
        CREATE TABLE IF NOT EXISTS coupon (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            code            VARCHAR NOT NULL UNIQUE,
            discount_type   VARCHAR NOT NULL CHECK (discount_type IN ('percent', 'fixed')),
            discount_value  DOUBLE PRECISION NOT NULL CHECK (discount_value > 0),
            min_order_amount DOUBLE PRECISION,
            max_uses        INTEGER,
            uses_count      INTEGER NOT NULL DEFAULT 0,
            store_id        UUID REFERENCES store(id) ON DELETE CASCADE,
            valid_from      DATE,
            valid_until     DATE,
            is_active       BOOLEAN NOT NULL DEFAULT TRUE,
            created_at      TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at      TIMESTAMP NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_coupon_code ON coupon(code)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_coupon_store_id ON coupon(store_id)")

    # -- deliveryzone table --
    op.execute("""
        CREATE TABLE IF NOT EXISTS deliveryzone (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            store_id    UUID NOT NULL UNIQUE REFERENCES store(id) ON DELETE CASCADE,
            latitude    DOUBLE PRECISION NOT NULL,
            longitude   DOUBLE PRECISION NOT NULL,
            radius_km   DOUBLE PRECISION NOT NULL CHECK (radius_km > 0),
            created_at  TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at  TIMESTAMP NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_deliveryzone_store_id ON deliveryzone(store_id)")

    # -- loyaltyaccount table --
    op.execute("""
        CREATE TABLE IF NOT EXISTS loyaltyaccount (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id         UUID NOT NULL UNIQUE REFERENCES "user"(id) ON DELETE CASCADE,
            points_balance  INTEGER NOT NULL DEFAULT 0,
            total_earned    INTEGER NOT NULL DEFAULT 0,
            total_redeemed  INTEGER NOT NULL DEFAULT 0,
            updated_at      TIMESTAMP NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_loyaltyaccount_user_id ON loyaltyaccount(user_id)")

    # -- loyaltytransaction table --
    op.execute("""
        CREATE TABLE IF NOT EXISTS loyaltytransaction (
            id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id          UUID NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
            order_id         UUID REFERENCES "order"(id) ON DELETE SET NULL,
            points           INTEGER NOT NULL,
            transaction_type VARCHAR NOT NULL CHECK (transaction_type IN ('earned', 'redeemed', 'adjusted')),
            description      TEXT NOT NULL,
            created_at       TIMESTAMP NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_loyaltytransaction_user_id ON loyaltytransaction(user_id)")

    # -- extend order table with discount fields --
    op.execute('ALTER TABLE "order" ADD COLUMN IF NOT EXISTS discount_amount DOUBLE PRECISION NOT NULL DEFAULT 0')
    op.execute('ALTER TABLE "order" ADD COLUMN IF NOT EXISTS points_redeemed INTEGER NOT NULL DEFAULT 0')
    op.execute('ALTER TABLE "order" ADD COLUMN IF NOT EXISTS coupon_code VARCHAR')


def downgrade() -> None:
    op.execute('ALTER TABLE "order" DROP COLUMN IF EXISTS coupon_code')
    op.execute('ALTER TABLE "order" DROP COLUMN IF EXISTS points_redeemed')
    op.execute('ALTER TABLE "order" DROP COLUMN IF EXISTS discount_amount')
    op.execute("DROP TABLE IF EXISTS loyaltytransaction")
    op.execute("DROP TABLE IF EXISTS loyaltyaccount")
    op.execute("DROP TABLE IF EXISTS deliveryzone")
    op.execute("DROP TABLE IF EXISTS coupon")
