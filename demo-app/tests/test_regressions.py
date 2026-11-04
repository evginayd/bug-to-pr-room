"""Regression tests added by the agents.

The repro agent writes a failing test here for each bug it reproduces, and
the fixer agent keeps it when it fixes the bug, so the bug cannot return.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app, reset_store

client = TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def clean_store():
    reset_store()
    yield
    reset_store()


def new_cart() -> int:
    response = client.post("/carts")
    assert response.status_code == 201
    return response.json()["id"]


def test_discount_save10_is_percentage_not_flat():
    """SAVE10 must deduct 10% of the subtotal, not a flat $10.

    One sticker pack costs $4.00; 10% off = $0.40 discount, total = $3.60.
    Before the fix the endpoint subtracts $10 flat, returning -$6.00.
    """
    cart_id = new_cart()
    client.post(f"/carts/{cart_id}/items", json={"product_id": "sticker", "quantity": 1})
    response = client.post(f"/carts/{cart_id}/discount", json={"code": "SAVE10"})
    assert response.status_code == 200
    assert response.json()["total"] == "3.60"


def test_discount_save10_on_hundred_dollar_cart():
    """SAVE10 on a $100.00 cart must yield $90.00 (10% = $10 off).

    Four t-shirts at $25.00 each = $100.00 subtotal; 10% off = $90.00.
    """
    cart_id = new_cart()
    client.post(f"/carts/{cart_id}/items", json={"product_id": "tshirt", "quantity": 4})
    response = client.post(f"/carts/{cart_id}/discount", json={"code": "SAVE10"})
    assert response.status_code == 200
    assert response.json()["total"] == "90.00"
