"""add sponsored posts

Revision ID: e2f3a4b5c6d7
Revises: d1e2f3a4b5c6
Create Date: 2026-08-22

"""
from alembic import op

revision = "e2f3a4b5c6d7"
down_revision = "d1e2f3a4b5c6"
branch_labels = None
depends_on = None

# Proposed default — SPEC_SPONSORED_POSTS.md §1. A constant seed value, not
# schema: easy to change via a fresh admin-set price after deploy, same
# posture as the ₹999 SubscriptionPlan seed in b3c4d5e6f7a8.
_INITIAL_PRICE_PAISE = 19900  # ₹199.00/post


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS sponsoredpostpricing (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            price_paise INTEGER NOT NULL,
            created_at  TIMESTAMP NOT NULL DEFAULT NOW(),
            created_by  VARCHAR NOT NULL DEFAULT 'admin'
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS sponsoredpost (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            store_id            UUID NOT NULL REFERENCES store(id) ON DELETE CASCADE,
            message             VARCHAR NOT NULL,
            amount_paise        INTEGER NOT NULL,
            status              VARCHAR NOT NULL DEFAULT 'pending',
            razorpay_order_id   VARCHAR,
            razorpay_payment_id VARCHAR,
            feed_post_id        UUID,
            created_at          TIMESTAMP NOT NULL DEFAULT NOW(),
            paid_at             TIMESTAMP
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_sponsoredpost_store_id ON sponsoredpost(store_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_sponsoredpost_status ON sponsoredpost(status)")

    op.execute(
        f"INSERT INTO sponsoredpostpricing (price_paise, created_by) "
        f"VALUES ({_INITIAL_PRICE_PAISE}, 'migration-seed')"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS sponsoredpost")
    op.execute("DROP TABLE IF EXISTS sponsoredpostpricing")
