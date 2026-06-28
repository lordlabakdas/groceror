"""Seed script: inserts the master product catalog into the DB."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlmodel import Session, select
from models.db import engine
from models.entity.inventory_entity import InventoryCategory
from models.entity.product_entity import Product

PRODUCTS = [
    {"name": "Bananas", "category": InventoryCategory.PRODUCE, "default_price": 1.29, "image_url": "https://images.unsplash.com/photo-1571771894821-ce9b6c11b08e?w=400&fit=crop"},
    {"name": "Carrots", "category": InventoryCategory.PRODUCE, "default_price": 0.99, "image_url": "https://images.unsplash.com/photo-1598170845058-32b9d6a5da37?w=400&fit=crop"},
    {"name": "Avocado", "category": InventoryCategory.PRODUCE, "default_price": 1.49, "image_url": "https://images.unsplash.com/photo-1523049673857-eb18f1d7b578?w=400&fit=crop"},
    {"name": "Tomatoes", "category": InventoryCategory.PRODUCE, "default_price": 2.49, "image_url": "https://images.unsplash.com/photo-1592841200221-a6898f307baa?w=400&fit=crop"},
    {"name": "Sourdough Bread", "category": InventoryCategory.BAKERY, "default_price": 4.99, "image_url": "https://images.unsplash.com/photo-1509440159596-0249088772ff?w=400&fit=crop"},
    {"name": "Croissants", "category": InventoryCategory.BAKERY, "default_price": 3.49, "image_url": "https://images.unsplash.com/photo-1555507036-ab1f4038808a?w=400&fit=crop"},
    {"name": "Whole Milk", "category": InventoryCategory.DAIRY, "default_price": 3.29, "image_url": "https://images.unsplash.com/photo-1563636619-e9143da7973b?w=400&fit=crop"},
    {"name": "Cheddar Cheese", "category": InventoryCategory.DAIRY, "default_price": 5.49, "image_url": "https://images.unsplash.com/photo-1618164435226-9e8e7ccfade7?w=400&fit=crop"},
    {"name": "Greek Yogurt", "category": InventoryCategory.DAIRY, "default_price": 2.99, "image_url": "https://images.unsplash.com/photo-1488477181946-6428a0291777?w=400&fit=crop"},
    {"name": "Chicken Breast", "category": InventoryCategory.MEAT, "default_price": 7.99, "image_url": "https://images.unsplash.com/photo-1604503468506-a8da13d82791?w=400&fit=crop"},
    {"name": "Salmon Fillet", "category": InventoryCategory.MEAT, "default_price": 12.99, "image_url": "https://images.unsplash.com/photo-1519708227418-c8fd9a32b7a2?w=400&fit=crop"},
    {"name": "Penne Pasta", "category": InventoryCategory.GROCERY, "default_price": 1.79, "image_url": "https://images.unsplash.com/photo-1621996346565-e3dbc646d9a9?w=400&fit=crop"},
    {"name": "Jasmine Rice", "category": InventoryCategory.GROCERY, "default_price": 3.49, "image_url": "https://images.unsplash.com/photo-1586201375761-83865001e31c?w=400&fit=crop"},
    {"name": "Olive Oil", "category": InventoryCategory.GROCERY, "default_price": 8.99, "image_url": "https://images.unsplash.com/photo-1474979266404-7eaacbcd87c5?w=400&fit=crop"},
    {"name": "Orange Juice", "category": InventoryCategory.GROCERY, "default_price": 4.29, "image_url": "https://images.unsplash.com/photo-1621506289937-a8e4df240d0b?w=400&fit=crop"},
    {"name": "Honey", "category": InventoryCategory.OTHER, "default_price": 6.99, "image_url": "https://images.unsplash.com/photo-1587049352846-4a222e784d38?w=400&fit=crop"},
    {"name": "Dark Chocolate", "category": InventoryCategory.OTHER, "default_price": 3.99, "image_url": "https://images.unsplash.com/photo-1548907040-4baa42d10919?w=400&fit=crop"},
]


def seed():
    with Session(engine) as session:
        inserted = 0
        for item in PRODUCTS:
            exists = session.exec(select(Product).where(Product.name == item["name"])).first()
            if exists:
                print(f"  ~ skipping (already exists): {item['name']}")
                continue
            session.add(Product(**item))
            print(f"  + {item['name']} ({item['category'].value})")
            inserted += 1
        session.commit()
        print(f"\nDone — inserted {inserted} products, skipped {len(PRODUCTS) - inserted}.")


if __name__ == "__main__":
    seed()
