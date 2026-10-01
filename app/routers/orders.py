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


def _get_order(db: Session, order_number: str, email: str | None) -> models.Order:
    order = db.query(models.Order).filter_by(order_number=order_number.upper()).first()
    # Email acts as a lightweight ownership check so order numbers alone can't be enumerated.
    if not order or (email is not None and order.customer_email.lower() != email.lower()):
        raise HTTPException(404, "Order not found")
    return order


@router.post("/checkout", response_model=schemas.OrderOut, status_code=201, summary="Turn a cart into an order")
def checkout(body: schemas.CheckoutIn, db: Session = Depends(get_db)):
    cart = db.get(models.Cart, body.cart_id)
    if not cart:
        raise HTTPException(404, "Cart not found")
    return services.order_out(services.create_order(db, cart, body))


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
    services.pay_order(db, order)
    return services.order_out(order)


@router.post("/orders/{order_number}/cancel", response_model=schemas.OrderOut, summary="Cancel an unshipped order")
def cancel_order(order_number: str, db: Session = Depends(get_db)):
    order = _get_order(db, order_number, None)
    services.cancel_order(db, order)
    return services.order_out(order)
