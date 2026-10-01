import random
import string
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import EmailStr
from sqlalchemy.orm import Session

from .. import models, schemas, services
from ..database import get_db

router = APIRouter(prefix="/api", tags=["checkout & orders"])


@router.get("/shipping-methods", response_model=list[schemas.ShippingMethodOut])
def list_shipping_methods():
    return [schemas.ShippingMethodOut(code=k, **v) for k, v in services.SHIPPING_METHODS.items()]


@router.get("/payment-methods", response_model=list[schemas.PaymentMethodOut])
def list_payment_methods():
    return [schemas.PaymentMethodOut(code=k, **v) for k, v in services.PAYMENT_METHODS.items()]


def _new_order_number(db: Session) -> str:
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    while True:
        suffix = "".join(random.choices(string.digits, k=5))
        number = f"SS-{today}-{suffix}"
        if not db.query(models.Order.id).filter_by(order_number=number).first():
            return number


def _get_order(db: Session, order_number: str, email: str | None) -> models.Order:
    order = db.query(models.Order).filter_by(order_number=order_number.upper()).first()
    # Email acts as a lightweight ownership check so order numbers alone can't be enumerated.
    if not order or (email is not None and order.customer_email.lower() != email.lower()):
        raise HTTPException(404, "Order not found")
    return order


@router.post("/checkout", response_model=schemas.OrderOut, status_code=201, summary="Turn a cart into an order")
def checkout(body: schemas.CheckoutIn, db: Session = Depends(get_db)):
    if body.shipping_method not in services.SHIPPING_METHODS:
        raise HTTPException(422, f"Unknown shipping method '{body.shipping_method}'")
    if body.payment_method not in services.PAYMENT_METHODS:
        raise HTTPException(422, f"Unknown payment method '{body.payment_method}'")

    cart = db.get(models.Cart, body.cart_id)
    if not cart:
        raise HTTPException(404, "Cart not found")
    if not cart.items:
        raise HTTPException(409, "Cart is empty")

    for it in cart.items:
        if it.quantity > it.variant.stock:
            raise HTTPException(
                409, f"{it.variant.product.name} ({it.variant.color_name}, {it.variant.size}): "
                     f"only {it.variant.stock} left"
            )

    totals = services.cart_out(db, cart, body.shipping_method).totals
    promo = services.find_promo(db, cart.promo_code)

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
    return services.order_out(order)


@router.get("/orders", response_model=list[schemas.OrderOut], summary="List orders for an email")
def list_orders(email: EmailStr, db: Session = Depends(get_db)):
    orders = (
        db.query(models.Order)
        .filter(models.Order.customer_email.ilike(str(email)))
        .order_by(models.Order.created_at.desc())
        .all()
    )
    return [services.order_out(o) for o in orders]


@router.get("/orders/{order_number}", response_model=schemas.OrderOut)
def get_order(
    order_number: str,
    email: str | None = Query(None, description="Customer email (recommended ownership check)"),
    db: Session = Depends(get_db),
):
    return services.order_out(_get_order(db, order_number, email))


@router.post("/orders/{order_number}/pay", response_model=schemas.OrderOut, summary="Simulate a successful payment")
def pay_order(order_number: str, db: Session = Depends(get_db)):
    order = _get_order(db, order_number, None)
    if order.status != "pending_payment":
        raise HTTPException(409, f"Order is '{order.status}', cannot be paid")
    order.status = "paid"
    order.paid_at = datetime.now(timezone.utc)
    db.commit()
    return services.order_out(order)


@router.post("/orders/{order_number}/cancel", response_model=schemas.OrderOut, summary="Cancel an unshipped order")
def cancel_order(order_number: str, db: Session = Depends(get_db)):
    order = _get_order(db, order_number, None)
    if order.status not in ("pending_payment", "paid"):
        raise HTTPException(409, f"Order is '{order.status}', cannot be cancelled")
    for it in order.items:
        if it.variant_id:
            variant = db.get(models.ProductVariant, it.variant_id)
            if variant:
                variant.stock += it.quantity
    order.status = "cancelled"
    db.commit()
    return services.order_out(order)
