"""enable RLS on all public tables

Revision ID: 0299fe7a78b5
Revises: f6b8d0e2a4c6
Create Date: 2026-07-11

Tables created via Alembic (as all of ours are) don't get Row Level
Security enabled by default — only tables created through the Supabase
Studio UI get prompted for it. Supabase's PostgREST layer grants baseline
privileges to the `anon`/`authenticated` roles on every table in `public`
regardless of how the table was created, so without RLS those roles can
read/write directly over the auto-generated REST API
(https://<project>.supabase.co/rest/v1/<table>), bypassing this app's own
JWT auth entirely.

None of these tables are meant to be queried directly by Supabase clients —
all access goes through the FastAPI layer, which connects as the `postgres`
role and is unaffected by RLS (table owners bypass RLS). Enabling RLS with
zero policies makes PostgREST access deny-all by default for anon/
authenticated, which is exactly the desired behavior here. If a table ever
needs direct client access in the future, add explicit policies for it then.

Flagged by the Supabase database linter ("RLS Disabled in Public").
"""
from alembic import op

revision = "0299fe7a78b5"
down_revision = "f6b8d0e2a4c6"
branch_labels = None
depends_on = None

# Every table in models/entity/, derived from each __tablename__ (explicit or
# default lowercase-classname). "order" and "user" are reserved words in
# Postgres and must stay quoted.
_TABLES = [
    "backinstockalert",
    "bulkrule",
    "bulkruleitem",
    "cartentity",
    "cartitementity",
    "coupon",
    "deliveryzone",
    "dispute",
    "disputemessage",
    "featuredstore",
    "flashsale",
    "inventory",
    "inventoryexpiry",
    "loyaltyaccount",
    "loyaltytransaction",
    '"order"',
    "orderitem",
    "phoneverification",
    "pricealert",
    "product",
    "productreview",
    "promotion",
    "scheduledorder",
    "scheduledorderitem",
    "stockthreshold",
    "store",
    "storefollow",
    "storerating",
    '"user"',
    "wishlistitem",
]


def upgrade() -> None:
    # ENABLE ROW LEVEL SECURITY is metadata-only and should be near-instant;
    # if it isn't, something else holds a lock on the table. Fail fast with
    # a clear "could not obtain lock" error instead of sitting until
    # statement_timeout cancels the query.
    op.execute("SET LOCAL lock_timeout = '5s'")
    for table in _TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    for table in _TABLES:
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
