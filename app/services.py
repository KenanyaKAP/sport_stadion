"""Business logic shared by the routers: serialization, pricing, shipping, payment."""

from sqlalchemy.orm import Session

from . import models, schemas

SHIPPING_METHODS: dict[str, dict] = {
    "regular": {
        "name": "Reguler",
        "description": "Pengiriman standar ke seluruh Indonesia.",
        "fee": 20_000,
        "free_over": 500_000,
        "eta_days": "3-5 hari",
    },
    "express": {
        "name": "Express",
        "description": "Prioritas, sampai lebih cepat.",
        "fee": 35_000,
        "free_over": None,
        "eta_days": "1-2 hari",
    },
    "same_day": {
        "name": "Same Day",
        "description": "Sampai hari ini untuk pesanan sebelum jam 14:00 (Jabodetabek).",
        "fee": 50_000,
        "free_over": None,
        "eta_days": "Hari ini",
    },
    "pickup": {
        "name": "Ambil di Toko",
        "description": "Ambil sendiri di Sport Stadion Senayan.",
        "fee": 0,
        "free_over": None,
        "eta_days": "Siap dalam 2 jam",
    },
}

PAYMENT_METHODS: dict[str, dict] = {
    "bank_transfer": {"name": "Transfer Bank (Virtual Account)", "description": "BCA, Mandiri, BNI, BRI."},
    "e_wallet": {"name": "E-Wallet", "description": "GoPay, OVO, DANA, ShopeePay."},
    "credit_card": {"name": "Kartu Kredit/Debit", "description": "Visa, Mastercard, JCB."},
}


def shipping_fee(method: str, subtotal_after_discount: int) -> int:
    m = SHIPPING_METHODS[method]
    if m["free_over"] is not None and subtotal_after_discount >= m["free_over"]:
        return 0
    return m["fee"]


def payment_instructions(order: models.Order) -> str | None:
    if order.status != "pending_payment":
        return None
    if order.payment_method == "bank_transfer":
        va = "8808" + "".join(c for c in order.order_number if c.isdigit())[-10:]
        return f"Transfer Rp{order.total:,} ke Virtual Account {va} (simulasi).".replace(",", ".")
    if order.payment_method == "e_wallet":
        return "Buka aplikasi e-wallet dan konfirmasi tagihan Sport Stadion (simulasi)."
    return "Selesaikan pembayaran kartu untuk memproses pesanan (simulasi)."


# ---------- Catalog ----------

def product_summary(p: models.Product) -> schemas.ProductSummary:
    prices = [v.price for v in p.variants] or [p.base_price]
    colors: dict[str, str] = {}
    sizes: list[str] = []
    for v in p.variants:
        colors.setdefault(v.color_name, v.color_hex)
        if v.size not in sizes:
            sizes.append(v.size)
    return schemas.ProductSummary(
        slug=p.slug,
        name=p.name,
        brand=p.brand.name,
        category=p.category.name,
        category_slug=p.category.slug,
        icon=p.icon or p.category.icon,
        sport=p.sport,
        gender=p.gender,
        short_description=p.short_description,
        price_min=min(prices),
        price_max=max(prices),
        compare_at_price=p.compare_at_price,
        rating=p.rating,
        review_count=p.review_count,
        colors=[schemas.ColorOption(name=n, hex=h) for n, h in colors.items()],
        sizes=sizes,
        in_stock=any(v.stock > 0 for v in p.variants),
    )


def product_detail(p: models.Product) -> schemas.ProductDetail:
    summary = product_summary(p)
    return schemas.ProductDetail(
        **summary.model_dump(),
        description=p.description,
        material=p.material,
        care_instructions=p.care_instructions,
        highlights=p.highlights or [],
        specs={k: str(v) for k, v in (p.specs or {}).items()},
        size_chart=p.category.size_chart,
        brand_info=schemas.BrandOut.model_validate(p.brand),
        variants=[
            schemas.VariantOut(
                id=v.id, sku=v.sku, color_name=v.color_name, color_hex=v.color_hex,
                size=v.size, price=v.price, stock=v.stock, in_stock=v.stock > 0,
            )
            for v in p.variants
        ],
    )


# ---------- Cart ----------

def find_promo(db: Session, code: str | None) -> models.PromoCode | None:
    if not code:
        return None
    return (
        db.query(models.PromoCode)
        .filter(models.PromoCode.code == code.strip().upper(), models.PromoCode.active.is_(True))
        .first()
    )


def compute_discount(promo: models.PromoCode | None, subtotal: int) -> int:
    if promo is None or subtotal < promo.min_subtotal:
        return 0
    discount = subtotal * promo.percent_off // 100 + promo.amount_off
    if promo.max_discount is not None:
        discount = min(discount, promo.max_discount)
    return min(discount, subtotal)


def cart_out(db: Session, cart: models.Cart, shipping_method: str | None = None) -> schemas.CartOut:
    items = []
    for it in cart.items:
        v = it.variant
        items.append(
            schemas.CartItemOut(
                id=it.id, variant_id=v.id, sku=v.sku,
                product_slug=v.product.slug, product_name=v.product.name,
                brand=v.product.brand.name, icon=v.product.icon or v.product.category.icon,
                color_name=v.color_name, color_hex=v.color_hex, size=v.size,
                unit_price=v.price, quantity=it.quantity, line_total=v.price * it.quantity,
                stock=v.stock,
            )
        )
    subtotal = sum(i.line_total for i in items)
    promo = find_promo(db, cart.promo_code)
    discount = compute_discount(promo, subtotal)
    fee = shipping_fee(shipping_method, subtotal - discount) if shipping_method and items else None

    promo_desc = None
    if promo:
        promo_desc = promo.description
        if subtotal < promo.min_subtotal:
            promo_desc += f" (belum aktif: minimal belanja Rp{promo.min_subtotal:,})".replace(",", ".")

    return schemas.CartOut(
        id=cart.id,
        items=items,
        item_count=sum(i.quantity for i in items),
        promo_code=cart.promo_code,
        promo_description=promo_desc,
        totals=schemas.Totals(
            subtotal=subtotal, discount=discount, shipping_fee=fee,
            total=subtotal - discount + (fee or 0),
        ),
    )


def order_out(order: models.Order) -> schemas.OrderOut:
    out = schemas.OrderOut.model_validate(order)
    out.payment_instructions = payment_instructions(order)
    return out
