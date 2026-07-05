"""add promotion and store rating tables

Revision ID: d4e5f6a7b8c9
Revises: bfb18f9f186d
Create Date: 2026-07-05

"""
from alembic import op

revision = "d4e5f6a7b8c9"
down_revision = "bfb18f9f186d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS promotion (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            inventory_id UUID NOT NULL UNIQUE REFERENCES inventory(id) ON DELETE CASCADE,
            sale_price DOUBLE PRECISION NOT NULL,
            start_date DATE NOT NULL,
            end_date DATE NOT NULL,
            created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL,
            updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL
        );

        CREATE TABLE IF NOT EXISTS storerating (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            store_id UUID NOT NULL REFERENCES store(id) ON DELETE CASCADE,
            user_id UUID NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
            rating INTEGER NOT NULL CHECK (rating >= 1 AND rating <= 5),
            comment TEXT,
            created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL,
            updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL,
            CONSTRAINT uq_store_rating_user UNIQUE (store_id, user_id)
        );
    """)


def downgrade() -> None:
    op.execute("""
        DROP TABLE IF EXISTS storerating;
        DROP TABLE IF EXISTS promotion;
    """)
