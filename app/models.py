"""SQLAlchemy ORM models for Sport Stadion."""

from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128))
    description: Mapped[str] = mapped_column(Text, default="")
    # Icon key used by the frontend to draw a product illustration (shoe, shirt, ball, ...).
    icon: Mapped[str] = mapped_column(String(32), default="box")
    # Size chart shared by all products in this category: {"headers": [...], "rows": [[...], ...]}
    size_chart: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    products: Mapped[list["Product"]] = relationship(back_populates="category")


class Brand(Base):
    __tablename__ = "brands"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128))
    country: Mapped[str] = mapped_column(String(64), default="")
    description: Mapped[str] = mapped_column(Text, default="")

    products: Mapped[list["Product"]] = relationship(back_populates="brand")


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"))
    brand_id: Mapped[int] = mapped_column(ForeignKey("brands.id"))
    # Optional override of the category icon (e.g. "cap" inside Aksesoris).
    icon: Mapped[str | None] = mapped_column(String(32), nullable=True)
    sport: Mapped[str] = mapped_column(String(64))  # running, football, basketball, ...
    gender: Mapped[str] = mapped_column(String(16))  # men, women, unisex, kids
    short_description: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text)
    material: Mapped[str] = mapped_column(String(300), default="")
    care_instructions: Mapped[str] = mapped_column(Text, default="")
    highlights: Mapped[list] = mapped_column(JSON, default=list)
    specs: Mapped[dict] = mapped_column(JSON, default=dict)  # free-form key -> value
    base_price: Mapped[int] = mapped_column(Integer)  # IDR
    compare_at_price: Mapped[int | None] = mapped_column(Integer, nullable=True)  # original price if discounted
    rating: Mapped[float] = mapped_column(default=0.0)
    review_count: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    category: Mapped[Category] = relationship(back_populates="products")
    brand: Mapped[Brand] = relationship(back_populates="products")
    variants: Mapped[list["ProductVariant"]] = relationship(
        back_populates="product", cascade="all, delete-orphan", order_by="ProductVariant.id"
    )


class ProductVariant(Base):
    """A purchasable SKU: one product in one colour and one size."""

    __tablename__ = "product_variants"
    __table_args__ = (UniqueConstraint("product_id", "color_name", "size"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    sku: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    color_name: Mapped[str] = mapped_column(String(64))
    color_hex: Mapped[str] = mapped_column(String(7))
    size: Mapped[str] = mapped_column(String(32))
    stock: Mapped[int] = mapped_column(Integer, default=0)
    price: Mapped[int] = mapped_column(Integer)  # IDR

    product: Mapped[Product] = relationship(back_populates="variants")


class PromoCode(Base):
    __tablename__ = "promo_codes"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    description: Mapped[str] = mapped_column(String(200))
    percent_off: Mapped[int] = mapped_column(Integer, default=0)
    amount_off: Mapped[int] = mapped_column(Integer, default=0)
    min_subtotal: Mapped[int] = mapped_column(Integer, default=0)
    max_discount: Mapped[int | None] = mapped_column(Integer, nullable=True)
    active: Mapped[bool] = mapped_column(default=True)


class Cart(Base):
    __tablename__ = "carts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)  # uuid4
    # Set for an account's cart (MCP / Conversify, one active cart per email); None for anonymous web carts.
    customer_email: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    promo_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    items: Mapped[list["CartItem"]] = relationship(
        back_populates="cart", cascade="all, delete-orphan", order_by="CartItem.id"
    )


class CartItem(Base):
    __tablename__ = "cart_items"
    __table_args__ = (UniqueConstraint("cart_id", "variant_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    cart_id: Mapped[str] = mapped_column(ForeignKey("carts.id", ondelete="CASCADE"))
    variant_id: Mapped[int] = mapped_column(ForeignKey("product_variants.id"))
    quantity: Mapped[int] = mapped_column(Integer)

    cart: Mapped[Cart] = relationship(back_populates="items")
    variant: Mapped[ProductVariant] = relationship()


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_number: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    # pending_payment -> paid -> shipped -> delivered ; or cancelled
    status: Mapped[str] = mapped_column(String(32), default="pending_payment")

    customer_name: Mapped[str] = mapped_column(String(128))
    customer_email: Mapped[str] = mapped_column(String(128), index=True)
    customer_phone: Mapped[str] = mapped_column(String(32))
    shipping_address: Mapped[dict] = mapped_column(JSON)
    shipping_method: Mapped[str] = mapped_column(String(32))
    payment_method: Mapped[str] = mapped_column(String(32))
    notes: Mapped[str] = mapped_column(Text, default="")

    promo_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    subtotal: Mapped[int] = mapped_column(Integer)
    discount: Mapped[int] = mapped_column(Integer, default=0)
    shipping_fee: Mapped[int] = mapped_column(Integer)
    total: Mapped[int] = mapped_column(Integer)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    items: Mapped[list["OrderItem"]] = relationship(
        back_populates="order", cascade="all, delete-orphan", order_by="OrderItem.id"
    )


class OrderItem(Base):
    """Snapshot of what was bought — survives later product/price changes."""

    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"))
    variant_id: Mapped[int | None] = mapped_column(ForeignKey("product_variants.id"), nullable=True)
    sku: Mapped[str] = mapped_column(String(64))
    product_name: Mapped[str] = mapped_column(String(200))
    product_slug: Mapped[str] = mapped_column(String(128))
    icon: Mapped[str] = mapped_column(String(32), default="box")
    color_name: Mapped[str] = mapped_column(String(64))
    color_hex: Mapped[str] = mapped_column(String(7))
    size: Mapped[str] = mapped_column(String(32))
    unit_price: Mapped[int] = mapped_column(Integer)
    quantity: Mapped[int] = mapped_column(Integer)
    line_total: Mapped[int] = mapped_column(Integer)

    order: Mapped[Order] = relationship(back_populates="items")
