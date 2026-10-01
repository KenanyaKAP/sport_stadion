"""MCP server for Sport Stadion, mounted at /mcp by app.main.

Designed for small on-device models (Conversify runs Qwen3.5-4B on iPhone):
few tools, short English descriptions, compact plain-text results, lenient input matching
(slug or name, "black" -> "Hitam", "eu 42" -> "42") and errors that tell the model what to do next.

The customer account is the `X-Customer-Email` request header (trust-based: this is a dummy store).
One account has one active cart, shared by every chat that sends the same email.
"""

import re
import uuid
from contextlib import contextmanager
from typing import Annotated, Literal

from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import Field, ValidationError
from sqlalchemy.orm import Session

from . import models, schemas, services
from .database import SessionLocal

ShippingMethod = Literal["regular", "express", "same_day", "pickup"]
PaymentMethod = Literal["bank_transfer", "e_wallet", "credit_card"]
assert set(ShippingMethod.__args__) == set(services.SHIPPING_METHODS)
assert set(PaymentMethod.__args__) == set(services.PAYMENT_METHODS)

ACCOUNT_HEADER = "x-customer-email"
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

READ_ONLY = ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=False)
WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False)


def _instructions() -> str:
    shipping = "; ".join(
        f"{code} ({m['name']}, {rp(m['fee']) if m['fee'] else 'free'}"
        + (f", free over {rp(m['free_over'])}" if m["free_over"] else "")
        + f", {m['eta_days']})"
        for code, m in services.SHIPPING_METHODS.items()
    )
    return (
        "You are the shopping assistant of Sport Stadion, an Indonesian sports store "
        "(shoes, apparel, balls, rackets, bags, accessories). Prices are in Indonesian Rupiah. "
        "Product data and colour names are in Indonesian (Hitam=black, Putih=white, Merah=red, Biru Navy=navy). "
        "Typical flow: search_products -> get_product_details (check colour/size stock) -> add_to_cart -> "
        "view_cart -> place_order. Ask for colour and size when the customer hasn't said. "
        "Before place_order, summarise items, total, shipping method, payment method and address, "
        "and wait for the customer's explicit confirmation. You cannot take payment: after ordering, "
        "share the payment instructions and the order link. "
        f"Shipping methods: {shipping}. Payment methods: bank_transfer, e_wallet, credit_card."
    )


# ---------- Formatting ----------

def rp(amount: int) -> str:
    return "Rp" + f"{amount:,}".replace(",", ".")


def _price(price_min: int, price_max: int) -> str:
    return rp(price_min) if price_min == price_max else f"{rp(price_min)}–{rp(price_max)}"


def _base_url(ctx: Context) -> str:
    headers = ctx.headers or {}
    host = headers.get("host", "localhost:8765")
    proto = headers.get("x-forwarded-proto", "http")
    return f"{proto}://{host}"


# ---------- Helpers ----------

@contextmanager
def _session():
    """DB session for one tool call; domain errors become tool errors the model can read."""
    db = SessionLocal()
    try:
        yield db
    except services.ServiceError as e:
        raise ToolError(e.message) from e
    finally:
        db.close()


def _account_email(ctx: Context) -> str:
    email = ((ctx.headers or {}).get(ACCOUNT_HEADER) or "").strip().lower()
    if not EMAIL_RE.match(email):
        raise ToolError(
            "No customer account: the client app must send the X-Customer-Email header. "
            "Tell the user to set their email in the app settings."
        )
    return email


def _account_cart(db: Session, email: str, create: bool = True) -> models.Cart | None:
    cart = (
        db.query(models.Cart)
        .filter(models.Cart.customer_email == email)
        .order_by(models.Cart.created_at.desc())
        .first()
    )
    if cart is None and create:
        cart = models.Cart(id=str(uuid.uuid4()), customer_email=email)
        db.add(cart)
        db.commit()
    return cart


def _resolve_product(db: Session, ref: str) -> models.Product:
    ref_clean = ref.strip().lower()
    products = services.product_query(db).all()
    for p in products:
        # Exact slug, exact name, or exact name without the brand ("Aero Glide 3").
        if ref_clean in (p.slug, p.name.lower(), p.name.lower().removeprefix(p.brand.name.lower() + " ")):
            return p
    words = [w for w in re.split(r"[\s\-]+", ref_clean) if w]
    matches = [p for p in products if all(w in f"{p.name} {p.slug}".lower() for w in words)]
    if len(matches) == 1:
        return matches[0]
    if matches:
        options = "; ".join(f"{p.name} (slug: {p.slug})" for p in matches[:6])
        raise ToolError(f"'{ref}' matches several products: {options}. Use the exact slug.")
    raise ToolError(f"No product matches '{ref}'. Use search_products to find the slug first.")


def _resolve_category(db: Session, ref: str) -> str:
    ref_clean = ref.strip().lower()
    cats = db.query(models.Category).all()
    for c in cats:
        if ref_clean in (c.slug, c.name.lower()):
            return c.slug
    partial = [c for c in cats if ref_clean in c.slug or ref_clean in c.name.lower()]
    if len(partial) == 1:
        return partial[0].slug
    options = ", ".join(c.slug for c in cats)
    raise ToolError(f"Unknown category '{ref}'. Categories: {options}.")


# English (and a few other) colour words the model may use -> Indonesian catalogue names.
COLOR_ALIASES = {
    "black": "hitam", "white": "putih", "red": "merah", "navy": "biru navy", "navy blue": "biru navy",
    "light blue": "biru muda", "sky blue": "biru muda", "grey": "abu-abu", "gray": "abu-abu", "abu": "abu-abu",
    "neon green": "hijau neon", "lime": "hijau neon", "army green": "hijau army", "olive": "hijau army",
    "orange": "oranye", "yellow": "kuning", "purple": "ungu", "cream": "krem", "beige": "krem",
    "teal": "tosca", "turquoise": "tosca", "maroon": "merah marun", "burgundy": "merah marun",
    "blue": "biru", "green": "hijau",
}


def _norm(text: str) -> str:
    return re.sub(r"\s+", "", text.lower())


def _match_color(product: models.Product, color: str) -> str:
    names = list(dict.fromkeys(v.color_name for v in product.variants))
    wanted = color.strip().lower()
    wanted = COLOR_ALIASES.get(wanted, wanted)
    exact = [n for n in names if n.lower() == wanted]
    if exact:
        return exact[0]
    partial = [n for n in names if wanted in n.lower()]
    if len(partial) == 1:
        return partial[0]
    raise ToolError(f"{product.name} has no colour '{color}'. Available colours: {', '.join(names)}.")


def _match_size(sizes: list[str], size: str) -> str | None:
    wanted = _norm(re.sub(r"^(eu|size|ukuran|uk)\s*", "", size.strip(), flags=re.I))
    for s in sizes:
        main, _, paren = s.partition(" (")
        if wanted in (_norm(s), _norm(main), _norm(paren.rstrip(")"))):
            return s
    return None


def _resolve_variant(product: models.Product, color: str, size: str) -> models.ProductVariant:
    color_name = _match_color(product, color)
    variants = [v for v in product.variants if v.color_name == color_name]
    size_label = _match_size([v.size for v in variants], size)
    if size_label is None:
        avail = ", ".join(v.size for v in variants if v.stock > 0) or "none"
        raise ToolError(f"{product.name} ({color_name}) has no size '{size}'. Sizes in stock: {avail}.")
    variant = next(v for v in variants if v.size == size_label)
    if variant.stock <= 0:
        others = ", ".join(v.size for v in variants if v.stock > 0) or "none"
        other_colors = sorted({v.color_name for v in product.variants if v.size == size_label and v.stock > 0})
        hint = f" Size {size_label} is available in: {', '.join(other_colors)}." if other_colors else ""
        raise ToolError(
            f"{product.name} {color_name} size {size_label} is sold out. "
            f"Other sizes in {color_name}: {others}.{hint}"
        )
    return variant


def _cart_text(db: Session, cart: models.Cart, base_url: str) -> str:
    out = services.cart_out(db, cart)
    if not out.items:
        return "The cart is empty."
    lines = [f"Cart ({out.item_count} item{'s' if out.item_count != 1 else ''}):"]
    for n, it in enumerate(out.items, 1):
        warn = f" [only {it.stock} left!]" if it.quantity > it.stock else ""
        lines.append(
            f"{n}. {it.product_name} — {it.color_name}, size {it.size} — "
            f"{it.quantity} × {rp(it.unit_price)} = {rp(it.line_total)}{warn}"
        )
    t = out.totals
    lines.append(f"Subtotal: {rp(t.subtotal)}")
    if out.promo_code:
        if t.discount:
            lines.append(f"Promo {out.promo_code}: -{rp(t.discount)}")
        else:
            lines.append(f"Promo {out.promo_code} not applied: {out.promo_description}")
    lines.append(f"Total before shipping: {rp(t.total)}")
    fees = ", ".join(
        f"{code} {rp(fee) if (fee := services.shipping_fee(code, t.total)) else 'FREE'}"
        for code in services.SHIPPING_METHODS
    )
    lines.append(f"Shipping options: {fees}")
    lines.append(f"Customer can also continue on the web: {base_url}/cart?cart={cart.id}")
    return "\n".join(lines)


def _order_text(order: models.Order, base_url: str, detailed: bool = True) -> str:
    ship = services.SHIPPING_METHODS[order.shipping_method]["name"]
    lines = [
        f"Order {order.order_number} — status: {order.status} — total {rp(order.total)} "
        f"— placed {order.created_at:%Y-%m-%d %H:%M} UTC"
    ]
    if detailed:
        for it in order.items:
            lines.append(f"- {it.product_name} — {it.color_name}, size {it.size} — {it.quantity} × {rp(it.unit_price)}")
        lines.append(
            f"Subtotal {rp(order.subtotal)}"
            + (f", discount -{rp(order.discount)} ({order.promo_code})" if order.discount else "")
            + f", shipping {ship} {rp(order.shipping_fee) if order.shipping_fee else 'FREE'}"
        )
        a = order.shipping_address
        lines.append(f"Ship to: {order.customer_name}, {a['street']}, {a['city']}, {a['province']} {a['postal_code']}")
        if instructions := services.payment_instructions(order):
            lines.append(f"Payment: {instructions}")
        lines.append(f"Order page (pay / track): {base_url}/order/{order.order_number}?email={order.customer_email}")
    return "\n".join(lines)


def _own_order(db: Session, email: str, order_number: str) -> models.Order:
    order = db.query(models.Order).filter_by(order_number=order_number.strip().upper()).first()
    if not order or order.customer_email.lower() != email:
        raise ToolError(f"Order '{order_number}' not found for this account. Call get_order_status without a number to list orders.")
    return order


# ---------- Server & tools ----------

mcp = MCPServer(
    name="Sport Stadion",
    title="Sport Stadion",
    description="Indonesian sports store: shoes, apparel, balls, rackets, bags and accessories.",
    version="1.0.0",
    instructions=_instructions(),
)


@mcp.tool(annotations=READ_ONLY, structured_output=False)
def search_products(
    query: Annotated[str | None, Field(description="Keywords, Indonesian works best, e.g. 'sepatu lari', 'jersey', 'raket'")] = None,
    category: Annotated[str | None, Field(description="Category slug or name, e.g. 'sepatu-lari', 'sepatu-bola', 'jersey-kaos', 'celana', 'bola', 'raket', 'tas', 'aksesoris'")] = None,
    gender: Literal["men", "women", "unisex", "kids"] | None = None,
    color: Annotated[str | None, Field(description="Colour, e.g. 'Hitam' or 'black'")] = None,
    size: Annotated[str | None, Field(description="Size, e.g. '42' (EU shoes) or 'M'")] = None,
    min_price: Annotated[int | None, Field(description="Rupiah")] = None,
    max_price: Annotated[int | None, Field(description="Rupiah")] = None,
    sort: Literal["relevance", "price_asc", "price_desc", "rating", "newest"] = "relevance",
    limit: Annotated[int, Field(ge=1, le=10)] = 5,
) -> str:
    """Search the catalogue. Returns matching products with slug, price, colours and sizes."""
    with _session() as db:
        filters = dict(
            category=_resolve_category(db, category) if category else None,
            gender=gender,
            min_price=min_price,
            max_price=max_price,
            sort=sort,
            in_stock=True,
        )
        if color:
            alias = COLOR_ALIASES.get(color.strip().lower(), color.strip().lower())
            known = {c for (c,) in db.query(models.ProductVariant.color_name).distinct()}
            filters["color"] = next((c for c in known if c.lower() == alias), color)
        if size:
            known_sizes = [s for (s,) in db.query(models.ProductVariant.size).distinct()]
            filters["size"] = _match_size(known_sizes, size) or size

        results = services.search_products(db, q=query, **filters)
        note = ""
        if not results and query:
            results = services.search_products(db, q=query, partial_match=True, **filters)
            note = "No product matched all keywords; showing closest matches.\n"
        if not results:
            return "No products found. Try fewer filters or different keywords."

        lines = [f"{note}Found {len(results)} product(s), showing {min(limit, len(results))}:"]
        for n, p in enumerate(results[:limit], 1):
            was = f" (was {rp(p.compare_at_price)})" if p.compare_at_price else ""
            lines.append(
                f"{n}. {p.name} — {_price(p.price_min, p.price_max)}{was}\n"
                f"   slug: {p.slug} | {p.brand} · {p.category} · {p.gender} | rating {p.rating}\n"
                f"   colours: {', '.join(c.name for c in p.colors)} | sizes: {', '.join(p.sizes)}"
            )
        if len(results) > limit:
            lines.append(f"{len(results) - limit} more — narrow the search or raise limit.")
        return "\n".join(lines)


@mcp.tool(annotations=READ_ONLY, structured_output=False)
def get_product_details(
    product: Annotated[str, Field(description="Product slug (preferred) or name")],
) -> str:
    """Full product info: description, specs, material, and stock per colour and size."""
    with _session() as db:
        p = _resolve_product(db, product)
        d = services.product_detail(p)
        was = f" (was {rp(d.compare_at_price)})" if d.compare_at_price else ""
        lines = [
            f"{d.name} (slug: {d.slug})",
            f"Brand: {d.brand} ({d.brand_info.country}) | Category: {d.category} | For: {d.gender} | Sport: {d.sport}",
            f"Price: {_price(d.price_min, d.price_max)}{was} | Rating {d.rating} ({d.review_count} reviews)",
            d.description,
        ]
        if d.highlights:
            lines.append("Highlights: " + "; ".join(d.highlights))
        if d.specs:
            lines.append("Specs: " + "; ".join(f"{k}: {v}" for k, v in d.specs.items()))
        lines.append(f"Material: {d.material}")
        lines.append("Stock by colour:")
        for color in d.colors:
            vs = [v for v in d.variants if v.color_name == color.name]
            avail = [f"{v.size} (only {v.stock} left)" if v.stock <= 5 else v.size for v in vs if v.stock > 0]
            sold = [v.size for v in vs if v.stock == 0]
            lines.append(
                f"- {color.name}: " + (", ".join(avail) if avail else "sold out")
                + (f" | sold out: {', '.join(sold)}" if sold and avail else "")
            )
        if d.price_min != d.price_max:
            by_size = dict.fromkeys(f"{v.size} {rp(v.price)}" for v in d.variants)
            lines.append("Price by size: " + ", ".join(by_size))
        if d.size_chart:
            lines.append("A size guide is available via get_size_guide.")
        return "\n".join(lines)


def _range_contains(cell: str, value: float) -> bool:
    nums = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", cell)]
    if len(nums) == 2:
        return nums[0] <= value <= nums[1] + 0.99
    return False


@mcp.tool(annotations=READ_ONLY, structured_output=False)
def get_size_guide(
    product: Annotated[str, Field(description="Product slug or name")],
    foot_length_cm: Annotated[float | None, Field(description="For shoes/socks: foot length heel to toe in cm")] = None,
    chest_cm: Annotated[float | None, Field(description="For apparel: chest circumference in cm")] = None,
) -> str:
    """Size chart for a product, plus a size recommendation if body measurements are given."""
    with _session() as db:
        p = _resolve_product(db, product)
        sizes = list(dict.fromkeys(v.size for v in p.variants))
        chart = p.category.size_chart
        if not chart:
            return f"{p.name} has no size chart. Available sizes: {', '.join(sizes)}."

        headers = chart["headers"]
        rows = [r for r in chart["rows"] if r[0] in sizes] or chart["rows"]
        lines = [f"{chart.get('title', 'Size guide')} for {p.name} (sizes sold: {', '.join(sizes)})", " | ".join(headers)]
        lines += [" | ".join(r) for r in rows]
        if chart.get("note"):
            lines.append(chart["note"])

        rec = None
        if foot_length_cm is not None:
            col = next((i for i, h in enumerate(headers) if "cm" in h.lower()), None)
            if col is not None:
                for r in rows:
                    nums = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", r[col])]
                    if nums and foot_length_cm <= nums[-1]:
                        rec = r[0]
                        break
        elif chest_cm is not None:
            col = next((i for i, h in enumerate(headers) if "dada" in h.lower() or "chest" in h.lower()), None)
            if col is not None:
                rec = next((r[0] for r in rows if _range_contains(r[col], chest_cm)), None)
                if rec is None and rows:
                    first = [float(x) for x in re.findall(r"\d+", rows[0][col])]
                    rec = rows[0][0] if first and chest_cm < first[0] else rows[-1][0]
        if rec:
            lines.append(f"Recommended size: {rec}.")
        elif foot_length_cm is not None or chest_cm is not None:
            lines.append("No size in this product fits that measurement exactly; suggest the closest and mention it.")
        return "\n".join(lines)


@mcp.tool(annotations=WRITE, structured_output=False)
def add_to_cart(
    product: Annotated[str, Field(description="Product slug (preferred) or name")],
    color: Annotated[str, Field(description="Colour name as listed for the product")],
    size: Annotated[str, Field(description="Size as listed for the product")],
    ctx: Context,
    quantity: Annotated[int, Field(ge=1, le=20)] = 1,
) -> str:
    """Add a product in a given colour and size to the customer's cart."""
    email = _account_email(ctx)
    with _session() as db:
        p = _resolve_product(db, product)
        variant = _resolve_variant(p, color, size)
        cart = _account_cart(db, email)
        services.add_to_cart(db, cart, variant, quantity)
        return f"Added {quantity} × {p.name} ({variant.color_name}, size {variant.size}).\n" + _cart_text(
            db, cart, _base_url(ctx)
        )


@mcp.tool(annotations=READ_ONLY, structured_output=False)
def view_cart(ctx: Context) -> str:
    """Show the customer's cart: numbered items, totals, shipping options and a web link."""
    email = _account_email(ctx)
    with _session() as db:
        cart = _account_cart(db, email, create=False)
        return _cart_text(db, cart, _base_url(ctx)) if cart else "The cart is empty."


@mcp.tool(annotations=WRITE, structured_output=False)
def update_cart_item(
    item_number: Annotated[int, Field(ge=1, description="Item number as shown by view_cart")],
    quantity: Annotated[int, Field(ge=0, le=20, description="New quantity; 0 removes the item")],
    ctx: Context,
) -> str:
    """Change the quantity of a cart item, or remove it with quantity 0."""
    email = _account_email(ctx)
    with _session() as db:
        cart = _account_cart(db, email, create=False)
        if not cart or not cart.items:
            return "The cart is empty."
        if item_number > len(cart.items):
            raise ToolError(f"The cart has only {len(cart.items)} item(s). Call view_cart to see the numbers.")
        item = cart.items[item_number - 1]
        name = f"{item.variant.product.name} ({item.variant.color_name}, size {item.variant.size})"
        services.set_item_quantity(db, cart, item, quantity)
        done = f"Removed {name}." if quantity == 0 else f"{name} quantity set to {quantity}."
        return f"{done}\n" + _cart_text(db, cart, _base_url(ctx))


@mcp.tool(annotations=WRITE, structured_output=False)
def apply_promo_code(
    code: Annotated[str, Field(description="Promo code; empty string removes the current code")],
    ctx: Context,
) -> str:
    """Apply a promo code to the customer's cart (or remove it with an empty code)."""
    email = _account_email(ctx)
    with _session() as db:
        cart = _account_cart(db, email)
        if not code.strip():
            cart.promo_code = None
            db.commit()
            return "Promo code removed.\n" + _cart_text(db, cart, _base_url(ctx))
        promo = services.apply_promo(db, cart, code)
        return f"Promo {promo.code} applied: {promo.description}.\n" + _cart_text(db, cart, _base_url(ctx))


@mcp.tool(
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False),
    structured_output=False,
)
def place_order(
    shipping_method: ShippingMethod,
    payment_method: PaymentMethod,
    ctx: Context,
    name: Annotated[str | None, Field(description="Recipient full name")] = None,
    phone: Annotated[str | None, Field(description="Phone number, e.g. 081234567890")] = None,
    street: Annotated[str | None, Field(description="Street address incl. house number")] = None,
    city: str | None = None,
    province: str | None = None,
    postal_code: Annotated[str | None, Field(description="5 digits")] = None,
    notes: str = "",
) -> str:
    """Place an order for everything in the cart. Only call after the customer explicitly confirmed
    items, total, shipping method, payment method and address. Name/phone/address can be omitted
    to reuse the customer's last order details."""
    email = _account_email(ctx)
    with _session() as db:
        cart = _account_cart(db, email, create=False)
        if not cart or not cart.items:
            raise ToolError("The cart is empty. Add products with add_to_cart first.")

        last = (
            db.query(models.Order)
            .filter(models.Order.customer_email == email)
            .order_by(models.Order.created_at.desc())
            .first()
        )
        given = {"name": name, "phone": phone, "street": street, "city": city,
                 "province": province, "postal_code": postal_code}
        previous = {"name": last.customer_name, "phone": last.customer_phone, **last.shipping_address} if last else {}
        fields = {k: v or previous.get(k) for k, v in given.items()}
        missing = [k for k, v in fields.items() if not v]
        if missing:
            raise ToolError(
                f"Missing customer details: {', '.join(missing)}. "
                "Ask the customer for them, then call place_order again with all details."
            )
        try:
            body = schemas.CheckoutIn(
                cart_id=cart.id,
                customer=schemas.CustomerIn(name=fields["name"], email=email, phone=fields["phone"]),
                shipping_address=schemas.Address(
                    street=fields["street"], city=fields["city"], province=fields["province"],
                    postal_code=fields["postal_code"],
                ),
                shipping_method=shipping_method,
                payment_method=payment_method,
                notes=notes,
            )
        except ValidationError as e:
            problems = "; ".join(f"{err['loc'][-1]}: {err['msg']}" for err in e.errors())
            raise ToolError(f"Invalid customer details ({problems}). Ask the customer to correct them.") from e

        order = services.create_order(db, cart, body)
        reused = [k for k, v in given.items() if not v]
        reused = f" (reused {', '.join(reused)} from the previous order)" if reused else ""
        return f"Order placed{reused}.\n" + _order_text(order, _base_url(ctx))


@mcp.tool(annotations=READ_ONLY, structured_output=False)
def get_order_status(
    ctx: Context,
    order_number: Annotated[str | None, Field(description="e.g. SS-20261001-12345; omit to list recent orders")] = None,
) -> str:
    """Status and details of one order, or the customer's 5 most recent orders."""
    email = _account_email(ctx)
    with _session() as db:
        if order_number:
            return _order_text(_own_order(db, email, order_number), _base_url(ctx))
        orders = (
            db.query(models.Order)
            .filter(models.Order.customer_email == email)
            .order_by(models.Order.created_at.desc())
            .limit(5)
            .all()
        )
        if not orders:
            return "This customer has no orders yet."
        return "Recent orders:\n" + "\n".join(_order_text(o, _base_url(ctx), detailed=False) for o in orders)


@mcp.tool(
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=False),
    structured_output=False,
)
def cancel_order(
    order_number: Annotated[str, Field(description="e.g. SS-20261001-12345")],
    ctx: Context,
) -> str:
    """Cancel an order that hasn't shipped yet. Confirm with the customer first."""
    email = _account_email(ctx)
    with _session() as db:
        order = _own_order(db, email, order_number)
        services.cancel_order(db, order)
        return f"Order {order.order_number} cancelled. Stock returned; any payment is refunded (simulated)."


# ---------- Schema compaction ----------
# Tool schemas are rendered into the model's prompt on every turn, so trim pydantic's noise:
# `anyOf: [X, null]` -> X, and drop `title` and `default: null`. Arguments are still validated by the
# tools' pydantic models (not by this advertised schema), so nulls and omitted values behave the same.

def _compact(schema: dict) -> dict:
    out = {}
    for key, value in schema.items():
        if key == "title" or (key == "default" and value is None):
            continue
        if key == "anyOf":
            non_null = [s for s in value if s.get("type") != "null"]
            if len(non_null) == 1:
                out.update(_compact(non_null[0]))
                continue
        if key == "properties":
            value = {name: _compact(prop) for name, prop in value.items()}
        elif isinstance(value, dict):
            value = _compact(value)
        out[key] = value
    return out


for _tool in mcp._tool_manager.list_tools():
    _tool.parameters = _compact(_tool.parameters)
