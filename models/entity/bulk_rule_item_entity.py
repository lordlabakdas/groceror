from typing import Optional
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel


class BulkRuleItem(SQLModel, table=True):
    __tablename__ = "bulkruleitem"

    id: Optional[UUID] = Field(default_factory=uuid4, primary_key=True)
    rule_id: UUID = Field(foreign_key="bulkrule.id", index=True)
    inventory_id: UUID = Field(foreign_key="inventory.id")
