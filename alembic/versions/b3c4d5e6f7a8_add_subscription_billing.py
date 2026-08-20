"""add subscription billing (Razorpay)

Revision ID: b3c4d5e6f7a8
Revises: a22a6b80ddeb
Create Date: 2026-08-19

See SPEC_SUBSCRIPTION.md for the design this implements.
"""

from alembic import op

revision = "b3c4d5e6f7a8"
down_revision = "a22a6b80ddeb"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -- subscriptionplan (append-only price history; current price = most
    # recent row) --
    op.execute("""
        CREATE TABLE IF NOT EXISTS subscriptionplan (
            id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            price_paise       INTEGER NOT NULL,
            razorpay_plan_id  VARCHAR,
            created_at        TIMESTAMP NOT NULL DEFAULT NOW(),
            created_by        VARCHAR NOT NULL DEFAULT 'admin'
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_subscriptionplan_created_at ON subscriptionplan(created_at)"
    )

    # -- subscription (one per store) --
    op.execute("""
        CREATE TABLE IF NOT EXISTS subscription (
            id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            store_id                 UUID NOT NULL UNIQUE REFERENCES store(id) ON DELETE CASCADE,
            status                   VARCHAR NOT NULL DEFAULT 'trialing'
                                     CHECK (status IN ('trialing','active','grace','locked','cancelled')),
            razorpay_customer_id     VARCHAR,
            razorpay_subscription_id VARCHAR,
            plan_price_paise         INTEGER,
            trial_end                TIMESTAMP NOT NULL,
            current_period_start     TIMESTAMP,
            current_period_end       TIMESTAMP,
            grace_period_end         TIMESTAMP,
            cancelled_at             TIMESTAMP,
            created_at               TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at               TIMESTAMP NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_subscription_store_id ON subscription(store_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_subscription_status ON subscription(status)")

    # -- subscriptioninvoice --
    op.execute("""
        CREATE TABLE IF NOT EXISTS subscriptioninvoice (
            id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            subscription_id      UUID NOT NULL REFERENCES subscription(id) ON DELETE CASCADE,
            razorpay_payment_id  VARCHAR,
            amount_paise         INTEGER NOT NULL,
            status               VARCHAR NOT NULL CHECK (status IN ('paid', 'failed')),
            period_start         TIMESTAMP NOT NULL,
            period_end           TIMESTAMP NOT NULL,
            paid_at              TIMESTAMP,
            created_at           TIMESTAMP NOT NULL DEFAULT NOW()
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_subscriptioninvoice_subscription_id ON subscriptioninvoice(subscription_id)"
    )

    # -- store.is_billing_locked --
    op.execute(
        "ALTER TABLE store ADD COLUMN IF NOT EXISTS is_billing_locked BOOLEAN NOT NULL DEFAULT FALSE"
    )

    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("ALTER TABLE subscriptionplan ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE subscription ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE subscriptioninvoice ENABLE ROW LEVEL SECURITY")

    # Seed the initial plan price (₹999.00/month) so subscription_service's
    # "current plan" lookup never has to handle "no plan exists yet".
    op.execute(
        "INSERT INTO subscriptionplan (price_paise, created_by) VALUES (99900, 'migration')"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE store DROP COLUMN IF EXISTS is_billing_locked")
    op.execute("DROP TABLE IF EXISTS subscriptioninvoice")
    op.execute("DROP TABLE IF EXISTS subscription")
    op.execute("DROP TABLE IF EXISTS subscriptionplan")
