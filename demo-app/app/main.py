"""Demo shop API: the codebase the agents work on.

A small in-memory shopping cart. It is deliberately simple so that a bug
report in the chat can be reproduced and fixed in a few minutes.

Business rules (the spec the agents check behaviour against):
- A cart line always has a quantity of at least 1.
- Discount code SAVE10 takes 10 percent off the cart subtotal.
- A discount code can be applied to a cart only once.
- Removing a product that is not in the cart answers 404.
"""

from decimal import Decimal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="Demo Shop API")

PRODUCTS: dict[str, dict] = {
    "mug": {"name": "Coffee mug", "price": Decimal("12.50")},
    "tshirt": {"name": "T-shirt", "price": Decimal("25.00")},
    "sticker": {"name": "Sticker pack", "price": Decimal("4.00")},
}

DISCOUNT_CODES: dict[str, Decimal] = {
    "SAVE10": Decimal("10"),  # percent off the subtotal
}

CARTS: dict[int, dict] = {}
_next_cart_id = 1


class AddItem(BaseModel):
    product_id: str
    quantity: int = 1


class UpdateItem(BaseModel):
    quantity: int


class ApplyDiscount(BaseModel):
    code: str


def _get_cart(cart_id: int) -> dict:
    cart = CARTS.get(cart_id)
    if cart is None:
        raise HTTPException(status_code=404, detail="Cart not found")
    return cart


def _subtotal(cart: dict) -> Decimal:
    return sum(
        (PRODUCTS[pid]["price"] * qty for pid, qty in cart["items"].items()),
        Decimal("0"),
    )


def _total(cart: dict) -> Decimal:
    total = _subtotal(cart)
    for code in cart["discounts"]:
        total -= DISCOUNT_CODES[code]
    return total.quantize(Decimal("0.01"))


def _view(cart_id: int, cart: dict) -> dict:
    return {
        "id": cart_id,
        "items": [
            {
                "product_id": pid,
                "name": PRODUCTS[pid]["name"],
                "quantity": qty,
                "line_total": str(PRODUCTS[pid]["price"] * qty),
            }
            for pid, qty in cart["items"].items()
        ],
        "discounts": list(cart["discounts"]),
        "subtotal": str(_subtotal(cart).quantize(Decimal("0.01"))),
        "total": str(_total(cart)),
    }


@app.get("/products")
def list_products() -> list[dict]:
    return [
        {"id": pid, "name": p["name"], "price": str(p["price"])}
        for pid, p in PRODUCTS.items()
    ]


@app.post("/carts", status_code=201)
def create_cart() -> dict:
    global _next_cart_id
    cart_id = _next_cart_id
    _next_cart_id += 1
    CARTS[cart_id] = {"items": {}, "discounts": []}
    return _view(cart_id, CARTS[cart_id])


@app.get("/carts/{cart_id}")
def get_cart(cart_id: int) -> dict:
    return _view(cart_id, _get_cart(cart_id))


@app.post("/carts/{cart_id}/items")
def add_item(cart_id: int, body: AddItem) -> dict:
    cart = _get_cart(cart_id)
    if body.product_id not in PRODUCTS:
        raise HTTPException(status_code=404, detail="Product not found")
    items = cart["items"]
    items[body.product_id] = items.get(body.product_id, 0) + body.quantity
    return _view(cart_id, cart)


@app.patch("/carts/{cart_id}/items/{product_id}")
def update_item(cart_id: int, product_id: str, body: UpdateItem) -> dict:
    cart = _get_cart(cart_id)
    if product_id not in cart["items"]:
        raise HTTPException(status_code=404, detail="Product not in cart")
    if body.quantity < 1:
        raise HTTPException(status_code=422, detail="Quantity must be at least 1")
    cart["items"][product_id] = body.quantity
    return _view(cart_id, cart)


@app.delete("/carts/{cart_id}/items/{product_id}")
def remove_item(cart_id: int, product_id: str) -> dict:
    cart = _get_cart(cart_id)
    del cart["items"][product_id]
    return _view(cart_id, cart)


@app.post("/carts/{cart_id}/discount")
def apply_discount(cart_id: int, body: ApplyDiscount) -> dict:
    cart = _get_cart(cart_id)
    code = body.code.upper()
    if code not in DISCOUNT_CODES:
        raise HTTPException(status_code=404, detail="Unknown discount code")
    cart["discounts"].append(code)
    return _view(cart_id, cart)


def reset_store() -> None:
    """Empty every cart. Used by the tests."""
    global _next_cart_id
    CARTS.clear()
    _next_cart_id = 1
