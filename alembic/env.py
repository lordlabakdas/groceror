from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy import create_engine
from sqlmodel import SQLModel
from alembic import context

# Import all models to populate SQLModel.metadata before autogenerate runs
from models.entity.phone_verification import PhoneVerification  # noqa: F401
from models.entity.user_entity import User  # noqa: F401
from models.entity.store_entity import Store  # noqa: F401
from models.entity.inventory_entity import Inventory  # noqa: F401
from models.entity.orders_entity import Order  # noqa: F401
from models.entity.order_item_entity import OrderItem  # noqa: F401
from models.entity.stock_threshold_entity import StockThreshold  # noqa: F401
from models.entity.inventory_expiry_entity import InventoryExpiry  # noqa: F401
from models.entity.cart_entity import CartEntity  # noqa: F401
from models.entity.cart_item_entity import CartItemEntity  # noqa: F401
from models.entity.product_entity import Product  # noqa: F401
from models.entity.promotion_entity import Promotion  # noqa: F401
from models.entity.store_rating_entity import StoreRating  # noqa: F401
from models.entity.coupon_entity import Coupon  # noqa: F401
from models.entity.delivery_zone_entity import DeliveryZone  # noqa: F401
from models.entity.loyalty_account_entity import LoyaltyAccount  # noqa: F401
from models.entity.loyalty_transaction_entity import LoyaltyTransaction  # noqa: F401
from models.entity.price_alert_entity import PriceAlert  # noqa: F401
from models.entity.featured_store_entity import FeaturedStore  # noqa: F401
from models.entity.dispute_entity import Dispute  # noqa: F401
from models.entity.dispute_message_entity import DisputeMessage  # noqa: F401
from models.entity.bulk_rule_entity import BulkRule  # noqa: F401
from models.entity.bulk_rule_item_entity import BulkRuleItem  # noqa: F401
from models.entity.wishlist_item_entity import WishlistItem  # noqa: F401
from models.entity.product_review_entity import ProductReview  # noqa: F401
from models.entity.scheduled_order_entity import ScheduledOrder  # noqa: F401
from models.entity.scheduled_order_item_entity import ScheduledOrderItem  # noqa: F401
from models.entity.store_follow_entity import StoreFollow  # noqa: F401
from models.entity.flash_sale_entity import FlashSale  # noqa: F401
from models.entity.back_in_stock_alert_entity import BackInStockAlert  # noqa: F401

alembic_cfg = context.config

if alembic_cfg.config_file_name is not None:
    fileConfig(alembic_cfg.config_file_name)

target_metadata = SQLModel.metadata


def get_url() -> str:
    from config import DBConfig
    return DBConfig.DB_URL


def run_migrations_offline() -> None:
    context.configure(
        url=get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(
        get_url(),
        connect_args={"options": "-c search_path=public"},
        poolclass=pool.NullPool,
    )
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
