from datetime import datetime
from math import floor
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field as PydanticField
from sqlmodel import select

from helpers.jwt import auth_required
from models.db import db_session
from models.entity.bulk_rule_entity import BulkRule
from models.entity.bulk_rule_item_entity import BulkRuleItem
from models.entity.inventory_entity import Inventory
from models.entity.phone_verification import PhoneVerification
from models.entity.store_entity import Store

bulk_rule_apis = APIRouter(prefix="/bulk-rules", tags=["bulk-rules"])


def _get_store(entity: PhoneVerification = Depends(auth_required)) -> Store:
    if entity.entity_type != "store":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Store access only")
    store = db_session.exec(select(Store).where(Store.entity_id == entity.id)).first()
    if not store:
        raise HTTPException(status_code=400, detail="Store profile not set")
    return store


# ── Payloads ────────────────────────────────────────────────────────────────

class CreateBXGFPayload(BaseModel):
    name: str
    inventory_id: UUID
    buy_quantity: int = PydanticField(..., ge=1)
    free_quantity: int = PydanticField(..., ge=1)


class CreateBundlePayload(BaseModel):
    name: str
    inventory_ids: List[UUID] = PydanticField(..., min_length=2)
    discount_type: str = PydanticField(..., pattern="^(percent|fixed)$")
    discount_value: float = PydanticField(..., gt=0)


# ── Responses ───────────────────────────────────────────────────────────────

class BulkRuleResponse(BaseModel):
    id: UUID
    store_id: UUID
    name: str
    rule_type: str
    is_active: bool
    # BXGF
    bxgf_inventory_id: Optional[UUID]
    bxgf_inventory_name: Optional[str]
    buy_quantity: Optional[int]
    free_quantity: Optional[int]
    # Bundle
    discount_type: Optional[str]
    discount_value: Optional[float]
    bundle_items: List[dict] = []   # [{inventory_id, name}]
    created_at: datetime


def _build_response(rule: BulkRule) -> BulkRuleResponse:
    bxgf_name = None
    if rule.bxgf_inventory_id:
        inv = db_session.exec(select(Inventory).where(Inventory.id == rule.bxgf_inventory_id)).first()
        bxgf_name = inv.name if inv else None

    items = db_session.exec(
        select(BulkRuleItem).where(BulkRuleItem.rule_id == rule.id)
    ).all()
    bundle_items = []
    for bi in items:
        inv = db_session.exec(select(Inventory).where(Inventory.id == bi.inventory_id)).first()
        bundle_items.append({"inventory_id": str(bi.inventory_id), "name": inv.name if inv else ""})

    return BulkRuleResponse(
        id=rule.id,
        store_id=rule.store_id,
        name=rule.name,
        rule_type=rule.rule_type,
        is_active=rule.is_active,
        bxgf_inventory_id=rule.bxgf_inventory_id,
        bxgf_inventory_name=bxgf_name,
        buy_quantity=rule.buy_quantity,
        free_quantity=rule.free_quantity,
        discount_type=rule.discount_type,
        discount_value=rule.discount_value,
        bundle_items=bundle_items,
        created_at=rule.created_at,
    )


# ── Endpoints ────────────────────────────────────────────────────────────────

@bulk_rule_apis.post("/bxgf", response_model=BulkRuleResponse)
def create_bxgf(payload: CreateBXGFPayload, store: Store = Depends(_get_store)):
    inv = db_session.exec(
        select(Inventory).where(Inventory.id == payload.inventory_id, Inventory.store_id == store.id)
    ).first()
    if not inv:
        raise HTTPException(status_code=404, detail="Inventory item not found in your store")

    rule = BulkRule(
        store_id=store.id,
        name=payload.name,
        rule_type="bxgf",
        bxgf_inventory_id=payload.inventory_id,
        buy_quantity=payload.buy_quantity,
        free_quantity=payload.free_quantity,
    )
    db_session.add(rule)
    db_session.commit()
    db_session.refresh(rule)
    return _build_response(rule)


@bulk_rule_apis.post("/bundle", response_model=BulkRuleResponse)
def create_bundle(payload: CreateBundlePayload, store: Store = Depends(_get_store)):
    for iid in payload.inventory_ids:
        inv = db_session.exec(
            select(Inventory).where(Inventory.id == iid, Inventory.store_id == store.id)
        ).first()
        if not inv:
            raise HTTPException(status_code=404, detail=f"Inventory item {iid} not found in your store")

    rule = BulkRule(
        store_id=store.id,
        name=payload.name,
        rule_type="bundle",
        discount_type=payload.discount_type,
        discount_value=payload.discount_value,
    )
    db_session.add(rule)
    db_session.flush()

    for iid in payload.inventory_ids:
        db_session.add(BulkRuleItem(rule_id=rule.id, inventory_id=iid))

    db_session.commit()
    db_session.refresh(rule)
    return _build_response(rule)


@bulk_rule_apis.get("", response_model=List[BulkRuleResponse])
def list_my_rules(store: Store = Depends(_get_store)):
    rules = db_session.exec(
        select(BulkRule).where(BulkRule.store_id == store.id, BulkRule.is_active == True)
    ).all()
    return [_build_response(r) for r in rules]


@bulk_rule_apis.get("/store/{store_id}", response_model=List[BulkRuleResponse])
def list_store_rules(store_id: UUID):
    rules = db_session.exec(
        select(BulkRule).where(BulkRule.store_id == store_id, BulkRule.is_active == True)
    ).all()
    return [_build_response(r) for r in rules]


@bulk_rule_apis.delete("/{rule_id}", status_code=204)
def deactivate_rule(rule_id: UUID, store: Store = Depends(_get_store)):
    rule = db_session.exec(
        select(BulkRule).where(BulkRule.id == rule_id, BulkRule.store_id == store.id)
    ).first()
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    rule.is_active = False
    db_session.commit()


# ── Helper used by order service ─────────────────────────────────────────────

def apply_bulk_rules(store_id: UUID, order_items: list) -> float:
    """
    order_items: list of objects with .inventory_id (UUID) and .quantity (int)
                 and .price (float, already resolved).
    Returns the total bulk discount amount.
    """
    rules = db_session.exec(
        select(BulkRule).where(BulkRule.store_id == store_id, BulkRule.is_active == True)
    ).all()

    qty_map = {item.inventory_id: item.quantity for item in order_items}
    price_map = {item.inventory_id: item.price for item in order_items}
    total_discount = 0.0

    for rule in rules:
        if rule.rule_type == "bxgf" and rule.bxgf_inventory_id in qty_map:
            qty = qty_map[rule.bxgf_inventory_id]
            cycle = rule.buy_quantity + rule.free_quantity
            free_units = floor(qty / cycle) * rule.free_quantity
            total_discount += free_units * price_map[rule.bxgf_inventory_id]

        elif rule.rule_type == "bundle":
            bundle_ids = {
                bi.inventory_id
                for bi in db_session.exec(
                    select(BulkRuleItem).where(BulkRuleItem.rule_id == rule.id)
                ).all()
            }
            if bundle_ids and bundle_ids.issubset(qty_map.keys()):
                bundle_subtotal = sum(qty_map[iid] * price_map[iid] for iid in bundle_ids)
                if rule.discount_type == "percent":
                    total_discount += round(bundle_subtotal * rule.discount_value / 100, 2)
                else:
                    total_discount += min(rule.discount_value, bundle_subtotal)

    return round(total_discount, 2)
