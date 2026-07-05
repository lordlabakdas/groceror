# models/service/orders_service.py
import logging
from datetime import date
from math import floor
from uuid import UUID, uuid4

from sqlmodel import select

from api.validators.order_validation import CreateOrderRequest
from models.db import db_session
from models.entity.coupon_entity import Coupon
from models.entity.inventory_entity import Inventory
from models.entity.loyalty_account_entity import LoyaltyAccount
from models.entity.loyalty_transaction_entity import LoyaltyTransaction
from models.entity.order_item_entity import OrderItem
from models.entity.orders_entity import Order as OrderEntity

logger = logging.getLogger(__name__)

# Points rules: 1 point per $1 spent; 100 points = $1 discount
POINTS_PER_DOLLAR = 1
POINTS_PER_DOLLAR_REDEMPTION = 100


def _get_or_create_loyalty_account(user_id: UUID) -> LoyaltyAccount:
    acct = db_session.exec(
        select(LoyaltyAccount).where(LoyaltyAccount.user_id == user_id)
    ).first()
    if not acct:
        acct = LoyaltyAccount(user_id=user_id)
        db_session.add(acct)
        db_session.flush()
    return acct


class OrderService:
    def create_order(self, order: CreateOrderRequest, current_user) -> tuple[OrderEntity, int]:
        """Create order, apply coupon/points, award points. Returns (order, points_earned)."""
        inv_ids = [item.inventory_id for item in order.items]
        inventory_rows = db_session.exec(
            select(Inventory).where(Inventory.id.in_(inv_ids))
        ).all()
        inventory_map = {inv.id: inv for inv in inventory_rows}

        missing = [str(iid) for iid in inv_ids if iid not in inventory_map]
        if missing:
            raise ValueError(f"Inventory items not found: {', '.join(missing)}")

        store_ids = {inventory_map[iid].store_id for iid in inv_ids}
        if len(store_ids) != 1:
            raise ValueError("All order items must belong to the same store")
        store_id = store_ids.pop()

        original_subtotal = round(
            sum(item.quantity * inventory_map[item.inventory_id].price for item in order.items), 2
        )

        # --- Bulk pricing rules (BXGF / bundle) ---
        from api.bulk_rule_api import apply_bulk_rules

        class _LineItem:
            def __init__(self, inventory_id, quantity, price):
                self.inventory_id = inventory_id
                self.quantity = quantity
                self.price = price

        line_items = [
            _LineItem(item.inventory_id, item.quantity, inventory_map[item.inventory_id].price)
            for item in order.items
        ]
        bulk_discount = apply_bulk_rules(store_id, line_items)
        # Coupon and loyalty apply to post-bulk subtotal
        subtotal = round(original_subtotal - bulk_discount, 2)

        # --- Coupon validation ---
        discount_amount = 0.0
        coupon_code = None
        coupon: Coupon | None = None
        if order.coupon_code:
            code = order.coupon_code.strip().upper()
            coupon = db_session.exec(
                select(Coupon).where(Coupon.code == code)
            ).first()
            if not coupon or not coupon.is_active:
                raise ValueError(f"Coupon '{code}' is not valid")
            today = date.today()
            if coupon.valid_from and today < coupon.valid_from:
                raise ValueError(f"Coupon '{code}' is not yet active")
            if coupon.valid_until and today > coupon.valid_until:
                raise ValueError(f"Coupon '{code}' has expired")
            if coupon.max_uses is not None and coupon.uses_count >= coupon.max_uses:
                raise ValueError(f"Coupon '{code}' has reached its usage limit")
            if coupon.min_order_amount and subtotal < coupon.min_order_amount:
                raise ValueError(
                    f"Coupon '{code}' requires a minimum order of ${coupon.min_order_amount:.2f}"
                )
            if coupon.store_id and coupon.store_id != store_id:
                raise ValueError(f"Coupon '{code}' is not valid for this store")

            if coupon.discount_type == "percent":
                discount_amount = round(subtotal * coupon.discount_value / 100, 2)
            else:
                discount_amount = min(coupon.discount_value, subtotal)
            coupon_code = code

        # --- Loyalty points redemption ---
        points_redeemed = 0
        loyalty_discount = 0.0
        if order.points_to_redeem > 0:
            acct = _get_or_create_loyalty_account(current_user.id)
            if order.points_to_redeem > acct.points_balance:
                raise ValueError(
                    f"Insufficient loyalty points (balance: {acct.points_balance})"
                )
            points_redeemed = order.points_to_redeem
            loyalty_discount = round(points_redeemed / POINTS_PER_DOLLAR_REDEMPTION, 2)

        coupon_loyalty_discount = min(discount_amount + loyalty_discount, subtotal)
        total_discount = round(bulk_discount + coupon_loyalty_discount, 2)
        total_price = round(original_subtotal - total_discount, 2)

        try:
            order_id = uuid4()
            order_entity = OrderEntity(
                id=order_id,
                order_date=order.order_date,
                user_id=current_user.id,
                store_id=store_id,
                total_price=total_price,
                discount_amount=round(total_discount, 2),
                points_redeemed=points_redeemed,
                coupon_code=coupon_code,
                status="pending",
            )
            db_session.add(order_entity)
            db_session.flush()

            for item in order.items:
                db_session.add(OrderItem(
                    order_id=order_id,
                    inventory_id=item.inventory_id,
                    quantity=item.quantity,
                    price=inventory_map[item.inventory_id].price,
                ))

            # Increment coupon uses_count
            if coupon:
                coupon.uses_count += 1
                db_session.add(coupon)

            # Apply loyalty redemption
            acct = _get_or_create_loyalty_account(current_user.id)
            if points_redeemed > 0:
                acct.points_balance -= points_redeemed
                acct.total_redeemed += points_redeemed
                db_session.add(LoyaltyTransaction(
                    user_id=current_user.id,
                    order_id=order_id,
                    points=-points_redeemed,
                    transaction_type="redeemed",
                    description=f"Redeemed for order #{order_id}",
                ))

            # Award points for spend (1 point per dollar of final total)
            points_earned = floor(total_price * POINTS_PER_DOLLAR)
            if points_earned > 0:
                acct.points_balance += points_earned
                acct.total_earned += points_earned
                acct.updated_at = __import__("datetime").datetime.utcnow()
                db_session.add(LoyaltyTransaction(
                    user_id=current_user.id,
                    order_id=order_id,
                    points=points_earned,
                    transaction_type="earned",
                    description=f"Earned for order #{order_id}",
                ))
            db_session.add(acct)

            db_session.commit()
            db_session.refresh(order_entity)
            return order_entity, points_earned
        except Exception as e:
            logger.error("Error creating order: %s", e)
            db_session.rollback()
            raise

    def get_order_by_id(self, order_id: UUID) -> OrderEntity:
        return db_session.exec(
            select(OrderEntity).where(OrderEntity.id == order_id)
        ).first()

    def get_orders_by_user(self, user_id: UUID) -> list[OrderEntity]:
        return db_session.exec(
            select(OrderEntity)
            .where(OrderEntity.user_id == user_id)
            .order_by(OrderEntity.order_date.desc())
        ).all()

    def get_orders_by_store(self, store_id: UUID) -> list[OrderEntity]:
        return db_session.exec(
            select(OrderEntity)
            .where(OrderEntity.store_id == store_id)
            .order_by(OrderEntity.order_date.desc())
        ).all()

    def update_order_status(self, order_id: UUID, store_id: UUID, new_status: str) -> OrderEntity:
        order = db_session.exec(
            select(OrderEntity)
            .where(OrderEntity.id == order_id)
            .where(OrderEntity.store_id == store_id)
        ).first()
        if not order:
            return None
        order.status = new_status
        db_session.commit()
        db_session.refresh(order)
        return order
