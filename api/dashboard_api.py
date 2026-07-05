import logging
from collections import Counter
from datetime import date, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import select

from api.helpers.inventory_helper import InventoryHelper
from api.validators.inventory_validation import (
    DashboardResponse,
    ExpiringItem,
    LowStockItem,
    TodaysOrder,
    TodaysSummary,
    TopSellerItem,
)
from helpers.jwt import auth_required
from models.db import db_session
from models.entity.inventory_entity import Inventory
from models.entity.inventory_expiry_entity import InventoryExpiry
from models.entity.order_item_entity import OrderItem
from models.entity.orders_entity import Order as OrderEntity
from models.entity.phone_verification import PhoneVerification
from models.entity.stock_threshold_entity import StockThreshold

logger = logging.getLogger(__name__)
dashboard_apis = APIRouter(prefix="/dashboard", tags=["dashboard"])

# Matches the frontend's hardcoded low-stock rule (quantity < 5) for items
# without an explicit per-item threshold.
DEFAULT_LOW_STOCK_THRESHOLD = 5


def _compute_top_sellers(
    order_items: list,
    inventory_map: dict,
    top_n: int = 5,
) -> list[TopSellerItem]:
    """Return top N sellers by units sold across the given order items."""
    counter: Counter = Counter()
    for oi in order_items:
        counter[oi.inventory_id] += oi.quantity

    result = []
    for inv_id, units_sold in counter.most_common():
        if len(result) >= top_n:
            break
        item = inventory_map.get(inv_id)
        if item:
            result.append(TopSellerItem(
                id=item.id,
                name=item.name,
                units_sold=units_sold,
                revenue=round(units_sold * item.price, 2),
            ))
    return result


@dashboard_apis.get("/", response_model=DashboardResponse)
async def get_dashboard(user: PhoneVerification = Depends(auth_required)):
    helper = InventoryHelper(user=user)
    try:
        store = helper._require_store()
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))

    inventory_items = db_session.exec(
        select(Inventory).where(Inventory.store_id == store.id)
    ).all()
    inventory_map: dict[UUID, Inventory] = {item.id: item for item in inventory_items}
    inventory_ids = list(inventory_map.keys())

    # --- Low stock -----------------------------------------------------------
    # Items with an explicit threshold are low when quantity <= threshold.
    # Items without one fall back to the default the frontend also uses
    # (quantity < 5), so Myventory and the dashboard always agree.
    low_stock: list[LowStockItem] = []
    if inventory_ids:
        threshold_rows = db_session.exec(
            select(StockThreshold).where(StockThreshold.inventory_id.in_(inventory_ids))
        ).all()
        explicit_thresholds = {t.inventory_id: t.threshold for t in threshold_rows}
        for item in inventory_items:
            threshold = explicit_thresholds.get(item.id)
            if threshold is not None:
                is_low = item.quantity <= threshold
            else:
                threshold = DEFAULT_LOW_STOCK_THRESHOLD
                is_low = item.quantity < DEFAULT_LOW_STOCK_THRESHOLD
            if is_low:
                low_stock.append(LowStockItem(
                    id=item.id, name=item.name,
                    quantity=item.quantity, threshold=threshold,
                ))

    # --- Today's orders ------------------------------------------------------
    today_utc = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    orders_today = db_session.exec(
        select(OrderEntity).where(
            OrderEntity.store_id == store.id,
            OrderEntity.order_date >= today_utc,
            OrderEntity.status != "cancelled",
        )
    ).all()
    revenue = round(sum(o.total_price for o in orders_today), 2)
    todays_summary = TodaysSummary(
        order_count=len(orders_today),
        revenue=revenue,
        orders=[
            TodaysOrder(
                id=o.id, total_price=o.total_price,
                status=o.status, order_date=o.order_date,
            )
            for o in sorted(orders_today, key=lambda o: o.order_date, reverse=True)[:20]
        ],
    )

    # --- Expiring soon (next 7 days) -----------------------------------------
    today = datetime.utcnow().date()
    cutoff = today + timedelta(days=7)
    expiring_soon: list[ExpiringItem] = []
    if inventory_ids:
        expiry_rows = db_session.exec(
            select(InventoryExpiry).where(
                InventoryExpiry.inventory_id.in_(inventory_ids),
                InventoryExpiry.expiry_date >= today,
                InventoryExpiry.expiry_date <= cutoff,
            )
        ).all()
        # Deduplicate: keep earliest expiry per inventory item
        seen_inventory_ids: set[UUID] = set()
        for e in sorted(expiry_rows, key=lambda r: r.expiry_date):
            if e.inventory_id in seen_inventory_ids:
                continue
            seen_inventory_ids.add(e.inventory_id)
            item = inventory_map.get(e.inventory_id)
            if item:
                expiring_soon.append(ExpiringItem(
                    id=item.id, name=item.name, quantity=item.quantity,
                    expiry_date=e.expiry_date,
                    days_remaining=(e.expiry_date - today).days,
                ))

    # --- Top sellers (last 7 days) -------------------------------------------
    week_start = today_utc - timedelta(days=7)
    recent_order_items = db_session.exec(
        select(OrderItem)
        .join(OrderEntity, OrderItem.order_id == OrderEntity.id)
        .where(
            OrderEntity.store_id == store.id,
            OrderEntity.order_date >= week_start,
            OrderEntity.status != "cancelled",
        )
    ).all()
    top_sellers = _compute_top_sellers(recent_order_items, inventory_map)

    return DashboardResponse(
        low_stock=low_stock,
        todays_summary=todays_summary,
        expiring_soon=expiring_soon,
        top_sellers=top_sellers,
    )
