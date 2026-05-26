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
from models.entity.orders_entity import Order as OrderEntity
from models.entity.phone_verification import PhoneVerification
from models.entity.stock_threshold_entity import StockThreshold

logger = logging.getLogger(__name__)
dashboard_apis = APIRouter(prefix="/dashboard", tags=["dashboard"])


def _compute_top_sellers(
    orders: list,
    inventory_map: dict,
    top_n: int = 5,
) -> list[TopSellerItem]:
    """Count item appearances across orders and return the top N sellers."""
    counter: Counter = Counter()
    for order in orders:
        for item_id_str in (order.items or []):
            counter[item_id_str] += 1

    result = []
    for item_id_str, count in counter.most_common(top_n):
        try:
            item_uuid = UUID(item_id_str)
        except ValueError:
            continue
        item = inventory_map.get(item_uuid)
        if item:
            result.append(TopSellerItem(
                id=item.id,
                name=item.name,
                units_sold=count,
                revenue=round(count * item.price, 2),
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
    low_stock: list[LowStockItem] = []
    if inventory_ids:
        thresholds = db_session.exec(
            select(StockThreshold).where(StockThreshold.inventory_id.in_(inventory_ids))
        ).all()
        for t in thresholds:
            item = inventory_map.get(t.inventory_id)
            if item and item.quantity <= t.threshold:
                low_stock.append(LowStockItem(
                    id=item.id, name=item.name,
                    quantity=item.quantity, threshold=t.threshold,
                ))

    # --- Today's orders ------------------------------------------------------
    today_start = datetime.combine(date.today(), datetime.min.time())
    orders_today = db_session.exec(
        select(OrderEntity).where(
            OrderEntity.store_id == store.id,
            OrderEntity.order_date >= today_start,
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
    today = date.today()
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
        for e in sorted(expiry_rows, key=lambda r: r.expiry_date):
            item = inventory_map.get(e.inventory_id)
            if item:
                expiring_soon.append(ExpiringItem(
                    id=item.id, name=item.name, quantity=item.quantity,
                    expiry_date=e.expiry_date,
                    days_remaining=(e.expiry_date - today).days,
                ))

    # --- Top sellers (last 7 days) -------------------------------------------
    week_start = datetime.combine(today - timedelta(days=7), datetime.min.time())
    recent_orders = db_session.exec(
        select(OrderEntity).where(
            OrderEntity.store_id == store.id,
            OrderEntity.order_date >= week_start,
        )
    ).all()
    top_sellers = _compute_top_sellers(recent_orders, inventory_map)

    return DashboardResponse(
        low_stock=low_stock,
        todays_summary=todays_summary,
        expiring_soon=expiring_soon,
        top_sellers=top_sellers,
    )
