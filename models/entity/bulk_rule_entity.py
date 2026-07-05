from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel

# rule_type = "bxgf"   → buy buy_quantity, get free_quantity free (on bxgf_inventory_id)
# rule_type = "bundle" → buy all items in BulkRuleItem, get discount_type/value off


class BulkRule(SQLModel, table=True):
    __tablename__ = "bulkrule"

    id: Optional[UUID] = Field(default_factory=uuid4, primary_key=True)
    store_id: UUID = Field(foreign_key="store.id", index=True)
    name: str
    rule_type: str                          # "bxgf" | "bundle"
    is_active: bool = Field(default=True)

    # BXGF-only
    bxgf_inventory_id: Optional[UUID] = Field(default=None, foreign_key="inventory.id")
    buy_quantity: Optional[int] = None
    free_quantity: Optional[int] = None

    # Bundle-only
    discount_type: Optional[str] = None    # "percent" | "fixed"
    discount_value: Optional[float] = None

    created_at: datetime = Field(default_factory=datetime.utcnow)
