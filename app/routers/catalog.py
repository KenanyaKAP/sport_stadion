from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import models, schemas, services
from ..database import get_db

router = APIRouter(prefix="/api", tags=["catalog"])

GENDERS = ["men", "women", "unisex", "kids"]


@router.get("/categories", response_model=list[schemas.CategoryOut])
def list_categories(db: Session = Depends(get_db)):
    counts = dict(
        db.query(models.Product.category_id, func.count(models.Product.id))
        .group_by(models.Product.category_id)
        .all()
    )
    return [
        schemas.CategoryOut(
            slug=c.slug, name=c.name, description=c.description, icon=c.icon,
            product_count=counts.get(c.id, 0),
        )
        for c in db.query(models.Category).order_by(models.Category.id)
    ]


@router.get("/brands", response_model=list[schemas.BrandOut])
def list_brands(db: Session = Depends(get_db)):
    return db.query(models.Brand).order_by(models.Brand.name).all()


@router.get("/facets", response_model=schemas.FacetsOut, summary="All filter values available in the catalog")
def facets(db: Session = Depends(get_db)):
    variants = (
        db.query(models.ProductVariant.color_name, models.ProductVariant.color_hex, models.ProductVariant.size)
        .distinct()
        .all()
    )
    prices = db.query(func.min(models.ProductVariant.price), func.max(models.ProductVariant.price)).one()
    sizes: list[str] = []
    colors: dict[str, str] = {}
    for name, hex_, s in variants:
        colors.setdefault(name, hex_)
        if s not in sizes:
            sizes.append(s)
    return schemas.FacetsOut(
        categories=list_categories(db),
        brands=list_brands(db),
        sports=sorted({s for (s,) in db.query(models.Product.sport).distinct()}),
        genders=[g for g in GENDERS if db.query(models.Product.id).filter_by(gender=g).first()],
        colors=[schemas.ColorOption(name=n, hex=colors[n]) for n in sorted(colors)],
        sizes=sizes,
        price_min=prices[0] or 0,
        price_max=prices[1] or 0,
    )


@router.get("/products", response_model=schemas.ProductPage, summary="Search & filter products")
def list_products(
    q: str | None = Query(None, description="Free-text search on name, brand, description"),
    category: str | None = Query(None, description="Category slug"),
    brand: str | None = Query(None, description="Brand slug"),
    sport: str | None = None,
    gender: str | None = Query(None, description="men | women | unisex | kids"),
    color: str | None = Query(None, description="Colour name, e.g. 'Hitam'"),
    size: str | None = Query(None, description="Size label, e.g. '42' or 'M'"),
    min_price: int | None = Query(None, ge=0),
    max_price: int | None = Query(None, ge=0),
    in_stock: bool = Query(False, description="Only products with at least one variant in stock"),
    sort: Literal["relevance", "newest", "price_asc", "price_desc", "rating"] = "relevance",
    page: int = Query(1, ge=1),
    page_size: int = Query(24, ge=1, le=100),
    db: Session = Depends(get_db),
):
    summaries = services.search_products(
        db, q=q, category=category, brand=brand, sport=sport, gender=gender, color=color, size=size,
        min_price=min_price, max_price=max_price, in_stock=in_stock, sort=sort,
    )
    start = (page - 1) * page_size
    return schemas.ProductPage(
        items=summaries[start : start + page_size],
        total=len(summaries),
        page=page,
        page_size=page_size,
    )


@router.get("/products/{slug}", response_model=schemas.ProductDetail, summary="Full product detail incl. variants")
def get_product(slug: str, db: Session = Depends(get_db)):
    product = services.product_query(db).filter(models.Product.slug == slug).first()
    if not product:
        raise HTTPException(404, f"Product '{slug}' not found")
    return services.product_detail(product)


@router.get("/variants/{sku}", response_model=schemas.VariantOut, summary="Look up a single SKU")
def get_variant(sku: str, db: Session = Depends(get_db)):
    v = db.query(models.ProductVariant).filter_by(sku=sku).first()
    if not v:
        raise HTTPException(404, f"SKU '{sku}' not found")
    return schemas.VariantOut(
        id=v.id, sku=v.sku, color_name=v.color_name, color_hex=v.color_hex,
        size=v.size, price=v.price, stock=v.stock, in_stock=v.stock > 0,
    )
