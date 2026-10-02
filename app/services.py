"""Business logic shared by the REST routers and the MCP server.

Functions raise `ServiceError` for expected failures; the REST layer turns it into an
HTTP error response and the MCP layer into a tool error the model can act on.
"""

import random
import string
from datetime import datetime, timezone

from sqlalchemy import and_, func
from sqlalchemy.orm import Session, selectinload

from . import models, schemas


class ServiceError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


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

SORTS = ("relevance", "newest", "price_asc", "price_desc", "rating")
GENDERS = ["men", "women", "unisex", "kids"]
APPAREL_SIZES = ["XS", "S", "M", "L", "XL", "XXL"]

# Colour words customers (or a model) may use -> Indonesian catalogue colour names.
COLOR_ALIASES = {
    "black": "hitam", "white": "putih", "red": "merah", "navy": "biru navy", "navy blue": "biru navy",
    "light blue": "biru muda", "sky blue": "biru muda", "grey": "abu-abu", "gray": "abu-abu", "abu": "abu-abu",
    "neon green": "hijau neon", "lime": "hijau neon", "army green": "hijau army", "olive": "hijau army",
    "orange": "oranye", "yellow": "kuning", "purple": "ungu", "cream": "krem", "beige": "krem",
    "teal": "tosca", "turquoise": "tosca", "maroon": "merah marun", "burgundy": "merah marun",
    "blue": "biru", "green": "hijau",
}

# English (and loose) search words -> the Indonesian words the catalogue uses.
QUERY_SYNONYMS = {
    "shoe": "sepatu", "shoes": "sepatu", "sneaker": "sepatu", "sneakers": "sepatu", "boots": "sepatu",
    "ball": "bola", "balls": "bola", "racket": "raket", "racquet": "raket",
    "bag": "tas", "backpack": "tas", "duffel": "tas", "shorts": "celana", "pants": "celana",
    "trousers": "celana", "sock": "kaos kaki", "socks": "kaos kaki", "bottle": "botol",
    "cap": "topi", "hat": "topi", "shirt": "kaos", "tshirt": "kaos", "t-shirt": "kaos", "tee": "kaos",
    "running": "lari", "jogging": "lari", "soccer": "bola", "kids": "anak", "accessories": "aksesoris",
    **COLOR_ALIASES,
}

# Indonesian / loose sport names -> the `sport` values products are tagged with.
SPORT_ALIASES = {
    "lari": "running", "jogging": "running", "run": "running", "trail": "trail running",
    "sepak bola": "football", "sepakbola": "football", "soccer": "football", "bola": "football",
    "basket": "basketball", "bola basket": "basketball", "voli": "volleyball", "bola voli": "volleyball",
    "volley": "volleyball", "bulutangkis": "badminton", "bulu tangkis": "badminton",
    "gym": "training", "fitness": "training", "latihan": "training",
}


def normalize_sport(sport: str) -> str:
    key = sport.strip().lower()
    return SPORT_ALIASES.get(key, key)


def product_query(db: Session):
    return db.query(models.Product).options(
        selectinload(models.Product.variants),
        selectinload(models.Product.brand),
        selectinload(models.Product.category),
    )


def _term_matches(term: str, text: str) -> bool:
    return term in text or (alt := QUERY_SYNONYMS.get(term)) is not None and alt in text


def _search_text(p: models.Product) -> str:
    colors = " ".join({v.color_name for v in p.variants})
    return " ".join(
        [p.name, p.short_description, p.description, p.sport, p.brand.name, p.category.name, colors]
    ).lower()


def search_products(
    db: Session,
    *,
    q: str | None = None,
    category: str | None = None,
    brand: str | None = None,
    sport: str | None = None,
    gender: str | None = None,
    color: str | None = None,
    size: str | None = None,
    min_price: int | None = None,
    max_price: int | None = None,
    in_stock: bool = False,
    on_sale: bool = False,
    sort: str = "relevance",
    partial_match: bool = False,
) -> list[schemas.ProductSummary]:
    """Filter + sort the catalog. Every word of `q` must match (name, description, brand,
    category, sport or colour; English words like "shoes" or "black" also match their Indonesian
    catalogue words). With `partial_match`, if nothing matches all words, products matching the
    most words are returned instead."""
    query = product_query(db).join(models.Product.brand).join(models.Product.category)
    if category:
        query = query.filter(models.Category.slug == category)
    if brand:
        query = query.filter(models.Brand.slug == brand)
    if sport:
        query = query.filter(func.lower(models.Product.sport) == normalize_sport(sport))
    if gender:
        query = query.filter(models.Product.gender == gender)
    if on_sale:
        query = query.filter(models.Product.compare_at_price.is_not(None))

    variant_filters = []
    if color:
        variant_filters.append(func.lower(models.ProductVariant.color_name) == color.lower())
    if size:
        variant_filters.append(func.lower(models.ProductVariant.size) == size.lower())
    if min_price is not None:
        variant_filters.append(models.ProductVariant.price >= min_price)
    if max_price is not None:
        variant_filters.append(models.ProductVariant.price <= max_price)
    if in_stock:
        variant_filters.append(models.ProductVariant.stock > 0)
    if variant_filters:
        query = query.filter(models.Product.variants.any(and_(*variant_filters)))

    products = query.all()

    if q and q.split():
        terms = [t.lower() for t in q.split()]
        texts = {p.id: _search_text(p) for p in products}
        scored = [(sum(_term_matches(t, texts[p.id]) for t in terms), p) for p in products]
        full = [p for score, p in scored if score == len(terms)]
        if full or not partial_match:
            products = full
        else:
            best = max((score for score, _ in scored), default=0)
            products = [p for score, p in scored if score == best and best > 0]

    summaries = [(p, product_summary(p)) for p in products]
    if sort == "newest":
        summaries.sort(key=lambda x: x[0].created_at, reverse=True)
    elif sort == "price_asc":
        summaries.sort(key=lambda x: x[1].price_min)
    elif sort == "price_desc":
        summaries.sort(key=lambda x: x[1].price_min, reverse=True)
    elif sort == "rating":
        summaries.sort(key=lambda x: (x[1].rating, x[1].review_count), reverse=True)
    else:  # relevance: in-stock first, then popularity
        summaries.sort(key=lambda x: (not x[1].in_stock, -x[1].review_count))
    return [s for _, s in summaries]


def sort_sizes(sizes: set[str] | list[str]) -> list[str]:
    """EU shoe sizes numerically, then apparel sizes XS–XXL, then everything else alphabetically."""
    def key(size: str):
        if size.isdigit():
            return (0, int(size), size)
        if size in APPAREL_SIZES:
            return (1, APPAREL_SIZES.index(size), size)
        return (2, 0, size)
    return sorted(set(sizes), key=key)


def catalog_facets(
    db: Session,
    *,
    category: str | None = None,
    brand: str | None = None,
    gender: str | None = None,
    sport: str | None = None,
) -> schemas.FacetsOut:
    """What the catalogue (or a slice of it) offers: categories and brands with product counts,
    sports, genders, colours, sizes, price range and stock/sale counts."""
    products = search_products(db, category=category, brand=brand, gender=gender, sport=sport)
    category_counts: dict[str, int] = {}
    brand_counts: dict[str, int] = {}
    colors: dict[str, str] = {}
    sizes: set[str] = set()
    for p in products:
        category_counts[p.category_slug] = category_counts.get(p.category_slug, 0) + 1
        brand_counts[p.brand_slug] = brand_counts.get(p.brand_slug, 0) + 1
        for c in p.colors:
            colors.setdefault(c.name, c.hex)
        sizes.update(p.sizes)

    categories = [
        schemas.CategoryOut(slug=c.slug, name=c.name, description=c.description, icon=c.icon,
                            product_count=category_counts[c.slug])
        for c in db.query(models.Category).order_by(models.Category.id)
        if c.slug in category_counts
    ]
    brands = [
        schemas.BrandOut(slug=b.slug, name=b.name, country=b.country, description=b.description,
                         product_count=brand_counts[b.slug])
        for b in db.query(models.Brand).order_by(models.Brand.name)
        if b.slug in brand_counts
    ]
    return schemas.FacetsOut(
        categories=categories,
        brands=brands,
        sports=sorted({p.sport for p in products}),
        genders=[g for g in GENDERS if any(p.gender == g for p in products)],
        colors=[schemas.ColorOption(name=n, hex=colors[n]) for n in sorted(colors)],
        sizes=sort_sizes(sizes),
        price_min=min((p.price_min for p in products), default=0),
        price_max=max((p.price_max for p in products), default=0),
        product_count=len(products),
        in_stock_count=sum(p.in_stock for p in products),
        on_sale_count=sum(p.compare_at_price is not None for p in products),
    )


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
        brand_slug=p.brand.slug,
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


def add_to_cart(db: Session, cart: models.Cart, variant: models.ProductVariant, quantity: int) -> None:
    item = next((i for i in cart.items if i.variant_id == variant.id), None)
    new_qty = (item.quantity if item else 0) + quantity
    if new_qty > variant.stock:
        in_cart = f" ({item.quantity} already in cart)" if item else ""
        raise ServiceError(409, f"Only {variant.stock} left in stock for {variant.sku}{in_cart}")
    if new_qty > 20:
        raise ServiceError(409, "Maximum 20 per item")
    if item:
        item.quantity = new_qty
    else:
        cart.items.append(models.CartItem(variant=variant, quantity=quantity))
    db.commit()


def set_item_quantity(db: Session, cart: models.Cart, item: models.CartItem, quantity: int) -> None:
    """Sets an item's quantity; 0 removes it."""
    if quantity == 0:
        cart.items.remove(item)
    else:
        if quantity > item.variant.stock:
            raise ServiceError(409, f"Only {item.variant.stock} left in stock for {item.variant.sku}")
        item.quantity = quantity
    db.commit()


def apply_promo(db: Session, cart: models.Cart, code: str) -> models.PromoCode:
    promo = find_promo(db, code)
    if not promo:
        raise ServiceError(404, f"Promo code '{code}' is invalid or expired")
    cart.promo_code = promo.code
    db.commit()
    return promo


# ---------- Orders ----------

def _new_order_number(db: Session) -> str:
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    while True:
        number = f"SS-{today}-{''.join(random.choices(string.digits, k=5))}"
        if not db.query(models.Order.id).filter_by(order_number=number).first():
            return number


def create_order(db: Session, cart: models.Cart, body: schemas.CheckoutIn) -> models.Order:
    """Turns the cart into an order: validates stock, snapshots items, decrements stock, deletes the cart."""
    if body.shipping_method not in SHIPPING_METHODS:
        raise ServiceError(422, f"Unknown shipping method '{body.shipping_method}'")
    if body.payment_method not in PAYMENT_METHODS:
        raise ServiceError(422, f"Unknown payment method '{body.payment_method}'")
    if not cart.items:
        raise ServiceError(409, "Cart is empty")
    for it in cart.items:
        if it.quantity > it.variant.stock:
            raise ServiceError(
                409, f"{it.variant.product.name} ({it.variant.color_name}, {it.variant.size}): "
                     f"only {it.variant.stock} left"
            )

    totals = cart_out(db, cart, body.shipping_method).totals
    promo = find_promo(db, cart.promo_code)
    order = models.Order(
        order_number=_new_order_number(db),
        customer_name=body.customer.name,
        customer_email=str(body.customer.email),
        customer_phone=body.customer.phone,
        shipping_address=body.shipping_address.model_dump(),
        shipping_method=body.shipping_method,
        payment_method=body.payment_method,
        notes=body.notes,
        promo_code=promo.code if promo and totals.discount else None,
        subtotal=totals.subtotal,
        discount=totals.discount,
        shipping_fee=totals.shipping_fee or 0,
        total=totals.total,
    )
    for it in cart.items:
        v = it.variant
        v.stock -= it.quantity
        order.items.append(
            models.OrderItem(
                variant_id=v.id, sku=v.sku, product_name=v.product.name, product_slug=v.product.slug,
                icon=v.product.icon or v.product.category.icon,
                color_name=v.color_name, color_hex=v.color_hex, size=v.size,
                unit_price=v.price, quantity=it.quantity, line_total=v.price * it.quantity,
            )
        )
    db.add(order)
    db.delete(cart)
    db.commit()
    return order


def pay_order(db: Session, order: models.Order) -> None:
    if order.status != "pending_payment":
        raise ServiceError(409, f"Order is '{order.status}', cannot be paid")
    order.status = "paid"
    order.paid_at = datetime.now(timezone.utc)
    db.commit()


def cancel_order(db: Session, order: models.Order) -> None:
    if order.status not in ("pending_payment", "paid"):
        raise ServiceError(409, f"Order is '{order.status}', cannot be cancelled")
    for it in order.items:
        if it.variant_id:
            variant = db.get(models.ProductVariant, it.variant_id)
            if variant:
                variant.stock += it.quantity
    order.status = "cancelled"
    db.commit()


def order_out(order: models.Order) -> schemas.OrderOut:
    out = schemas.OrderOut.model_validate(order)
    out.payment_instructions = payment_instructions(order)
    return out
