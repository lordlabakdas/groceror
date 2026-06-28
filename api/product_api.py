import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import select

from api.validators.product_validation import (
    AddProductPayload,
    ProductItem,
    ProductListResponse,
    ProductResponse,
)
from helpers.jwt import auth_required
from models.db import db_session
from models.entity.inventory_entity import InventoryCategory
from models.entity.phone_verification import PhoneVerification
from models.entity.product_entity import Product

logger = logging.getLogger(__name__)
product_apis = APIRouter(prefix="/products", tags=["products"])


@product_apis.get("", response_model=ProductListResponse)
async def list_products(
    category: Optional[InventoryCategory] = Query(default=None),
    q: Optional[str] = Query(default=None, min_length=2),
):
    stmt = select(Product)
    if category:
        stmt = stmt.where(Product.category == category)
    if q:
        stmt = stmt.where(Product.name.ilike(f"%{q}%"))
    products = db_session.exec(stmt).all()
    return ProductListResponse(
        products=[
            ProductItem(
                id=p.id,
                name=p.name,
                category=p.category,
                image_url=p.image_url,
                default_price=p.default_price,
            )
            for p in products
        ]
    )


@product_apis.get("/{product_id}", response_model=ProductItem)
async def get_product(product_id: UUID):
    product = db_session.exec(select(Product).where(Product.id == product_id)).first()
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    return ProductItem(
        id=product.id,
        name=product.name,
        category=product.category,
        image_url=product.image_url,
        default_price=product.default_price,
    )


@product_apis.post("", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
async def add_product(
    payload: AddProductPayload,
    user: PhoneVerification = Depends(auth_required),
):
    existing = db_session.exec(select(Product).where(Product.name == payload.name)).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Product '{payload.name}' already exists",
        )
    product = Product(
        name=payload.name,
        category=payload.category,
        image_url=payload.image_url,
        default_price=payload.default_price,
    )
    db_session.add(product)
    db_session.commit()
    db_session.refresh(product)
    logger.info(f"Product created: {product.name} (id={product.id})")
    return ProductResponse(product_id=product.id)
