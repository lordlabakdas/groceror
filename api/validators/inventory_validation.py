from datetime import date, datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field as PydanticField

from models.entity.inventory_entity import InventoryCategory


class AddInventoryPayload(BaseModel):
    name: str
    quantity: int
    category: InventoryCategory
    price: float = 0.0
    notes: Optional[str] = None


class AddInventoryResponse(BaseModel):
    inventory_id: UUID


class StoreInventory(BaseModel):
    id: UUID
    name: str
    quantity: int
    category: InventoryCategory
    price: float
    store_id: UUID
    notes: Optional[str] = None
    expiry_date: Optional[date] = None
    sale_price: Optional[float] = None  # active promotion price, if any


class StoreInventoryResponse(BaseModel):
    inventory: List[StoreInventory]


class UpdateInventoryPayload(BaseModel):
    quantity: Optional[int] = None
    price: Optional[float] = None


class UpdateInventoryResponse(BaseModel):
    status: str


class DeleteInventoryResponse(BaseModel):
    status: str


class SearchResultItem(BaseModel):
    id: UUID
    name: str
    category: InventoryCategory
    price: float
    quantity: int
    notes: Optional[str]
    store_id: UUID
    store_name: str
    sale_price: Optional[float] = None


class SetPromotionPayload(BaseModel):
    sale_price: float = PydanticField(gt=0)
    start_date: date
    end_date: date


class SearchResponse(BaseModel):
    query: str
    results: List[SearchResultItem]


# ---------------------------------------------------------------------------
# Dashboard validators
# ---------------------------------------------------------------------------


class SetThresholdPayload(BaseModel):
    threshold: int = PydanticField(ge=0)


class SetExpiryPayload(BaseModel):
    expiry_date: date


class LowStockItem(BaseModel):
    id: UUID
    name: str
    quantity: int
    threshold: int


class TodaysOrder(BaseModel):
    id: UUID
    total_price: float
    status: str
    order_date: datetime


class TodaysSummary(BaseModel):
    order_count: int
    revenue: float
    orders: List[TodaysOrder]


class ExpiringItem(BaseModel):
    id: UUID
    name: str
    quantity: int
    expiry_date: date
    days_remaining: int = PydanticField(ge=0)


class TopSellerItem(BaseModel):
    id: UUID
    name: str
    units_sold: int
    revenue: float


class DashboardResponse(BaseModel):
    low_stock: List[LowStockItem]
    todays_summary: TodaysSummary
    expiring_soon: List[ExpiringItem]
    top_sellers: List[TopSellerItem]


class RevenueTrendPoint(BaseModel):
    date: date
    revenue: float
    order_count: int


class RevenueTrendResponse(BaseModel):
    trend: List[RevenueTrendPoint]
