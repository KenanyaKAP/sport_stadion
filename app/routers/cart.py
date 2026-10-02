import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from .. import models, schemas, services
from ..database import get_db

router = APIRouter(prefix="/api/carts", tags=["cart"])


def _get_cart(db: Session, cart_id: str) -> models.Cart:
    cart = db.get(models.Cart, cart_id)
    if not cart:
        raise HTTPException(404, f"Cart '{cart_id}' not found")
    return cart


def _check_shipping(method: str | None):
    if method and method not in services.SHIPPING_METHODS:
        raise HTTPException(422, f"Unknown shipping method '{method}'")


@router.post("", response_model=schemas.CartOut, status_code=201, summary="Create an empty cart")
def create_cart(db: Session = Depends(get_db)):
    cart = models.Cart(id=str(uuid.uuid4()))
    db.add(cart)
    db.commit()
    return services.cart_out(db, cart)


@router.post("/account", response_model=schemas.CartOut, summary="Sign in: get (or create) an account's cart")
def account_cart(body: schemas.AccountCartIn, db: Session = Depends(get_db)):
    """The same cart Conversify chats use for this email. An anonymous cart can be merged in."""
    cart = services.account_cart(db, str(body.email))
    if body.merge_cart_id and body.merge_cart_id != cart.id:
        source = db.get(models.Cart, body.merge_cart_id)
        if source and source.customer_email is None:
            services.merge_cart(db, source, cart)
    return services.cart_out(db, cart)


@router.get("/{cart_id}", response_model=schemas.CartOut)
def get_cart(
    cart_id: str,
    shipping_method: str | None = Query(None, description="Include shipping fee for this method in totals"),
    db: Session = Depends(get_db),
):
    _check_shipping(shipping_method)
    return services.cart_out(db, _get_cart(db, cart_id), shipping_method)


@router.post("/{cart_id}/items", response_model=schemas.CartOut, summary="Add a variant to the cart")
def add_item(cart_id: str, body: schemas.CartItemIn, db: Session = Depends(get_db)):
    cart = _get_cart(db, cart_id)
    if body.variant_id is not None:
        variant = db.get(models.ProductVariant, body.variant_id)
    elif body.sku:
        variant = db.query(models.ProductVariant).filter_by(sku=body.sku).first()
    else:
        raise HTTPException(422, "Provide variant_id or sku")
    if not variant:
        raise HTTPException(404, "Variant not found")

    services.add_to_cart(db, cart, variant, body.quantity)
    return services.cart_out(db, cart)


@router.patch("/{cart_id}/items/{item_id}", response_model=schemas.CartOut, summary="Change quantity (0 removes)")
def update_item(cart_id: str, item_id: int, body: schemas.CartItemUpdate, db: Session = Depends(get_db)):
    cart = _get_cart(db, cart_id)
    item = next((i for i in cart.items if i.id == item_id), None)
    if not item:
        raise HTTPException(404, "Cart item not found")
    services.set_item_quantity(db, cart, item, body.quantity)
    return services.cart_out(db, cart)


@router.delete("/{cart_id}/items/{item_id}", response_model=schemas.CartOut)
def remove_item(cart_id: str, item_id: int, db: Session = Depends(get_db)):
    return update_item(cart_id, item_id, schemas.CartItemUpdate(quantity=0), db)


@router.post("/{cart_id}/promo", response_model=schemas.CartOut, summary="Apply a promo code")
def apply_promo(cart_id: str, body: schemas.PromoIn, db: Session = Depends(get_db)):
    cart = _get_cart(db, cart_id)
    services.apply_promo(db, cart, body.code)
    return services.cart_out(db, cart)


@router.delete("/{cart_id}/promo", response_model=schemas.CartOut)
def remove_promo(cart_id: str, db: Session = Depends(get_db)):
    cart = _get_cart(db, cart_id)
    cart.promo_code = None
    db.commit()
    return services.cart_out(db, cart)
