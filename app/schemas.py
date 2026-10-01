"""Pydantic request/response schemas. All money values are integers in IDR."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------- Catalog ----------

class CategoryOut(ORM):
    slug: str
    name: str
    description: str
    icon: str
    product_count: int = 0


class BrandOut(ORM):
    slug: str
    name: str
    country: str
    description: str


class VariantOut(ORM):
    id: int
    sku: str
    color_name: str
    color_hex: str
    size: str
    price: int
    stock: int
    in_stock: bool


class ColorOption(BaseModel):
    name: str
    hex: str


class ProductSummary(BaseModel):
    slug: str
    name: str
    brand: str
    category: str
    category_slug: str
    icon: str
    sport: str
    gender: str
    short_description: str
    price_min: int
    price_max: int
    compare_at_price: int | None
    rating: float
    review_count: int
    colors: list[ColorOption]
    sizes: list[str]
    in_stock: bool


class ProductDetail(ProductSummary):
    description: str
    material: str
    care_instructions: str
    highlights: list[str]
    specs: dict[str, str]
    size_chart: dict | None
    brand_info: BrandOut
    variants: list[VariantOut]


class ProductPage(BaseModel):
    items: list[ProductSummary]
    total: int
    page: int
    page_size: int


class FacetsOut(BaseModel):
    categories: list[CategoryOut]
    brands: list[BrandOut]
    sports: list[str]
    genders: list[str]
    colors: list[ColorOption]
    sizes: list[str]
    price_min: int
    price_max: int


# ---------- Cart ----------

class CartItemIn(BaseModel):
    variant_id: int | None = Field(None, description="Variant id. Either variant_id or sku is required.")
    sku: str | None = None
    quantity: int = Field(1, ge=1, le=20)


class CartItemUpdate(BaseModel):
    quantity: int = Field(..., ge=0, le=20, description="0 removes the item.")


class PromoIn(BaseModel):
    code: str


class CartItemOut(BaseModel):
    id: int
    variant_id: int
    sku: str
    product_slug: str
    product_name: str
    brand: str
    icon: str
    color_name: str
    color_hex: str
    size: str
    unit_price: int
    quantity: int
    line_total: int
    stock: int


class Totals(BaseModel):
    subtotal: int
    discount: int
    shipping_fee: int | None = None
    total: int


class CartOut(BaseModel):
    id: str
    items: list[CartItemOut]
    item_count: int
    promo_code: str | None
    promo_description: str | None
    totals: Totals


# ---------- Checkout / Orders ----------

class ShippingMethodOut(BaseModel):
    code: str
    name: str
    description: str
    fee: int
    free_over: int | None
    eta_days: str


class PaymentMethodOut(BaseModel):
    code: str
    name: str
    description: str


class Address(BaseModel):
    street: str = Field(..., min_length=3)
    city: str = Field(..., min_length=2)
    province: str = Field(..., min_length=2)
    postal_code: str = Field(..., pattern=r"^\d{5}$")
    country: str = "Indonesia"


class CustomerIn(BaseModel):
    name: str = Field(..., min_length=2)
    email: EmailStr
    phone: str = Field(..., pattern=r"^\+?[0-9 \-]{8,20}$")


class CheckoutIn(BaseModel):
    cart_id: str
    customer: CustomerIn
    shipping_address: Address
    shipping_method: str = "regular"
    payment_method: str = "bank_transfer"
    notes: str = ""


class OrderItemOut(ORM):
    sku: str
    product_name: str
    product_slug: str
    icon: str
    color_name: str
    color_hex: str
    size: str
    unit_price: int
    quantity: int
    line_total: int


class OrderOut(ORM):
    order_number: str
    status: Literal["pending_payment", "paid", "shipped", "delivered", "cancelled"]
    customer_name: str
    customer_email: str
    customer_phone: str
    shipping_address: dict
    shipping_method: str
    payment_method: str
    notes: str
    promo_code: str | None
    subtotal: int
    discount: int
    shipping_fee: int
    total: int
    created_at: datetime
    paid_at: datetime | None
    items: list[OrderItemOut]
    payment_instructions: str | None = None
