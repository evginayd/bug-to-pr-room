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


def test_remove_item_not_in_cart_returns_404():
    """DELETE an item that was never added to the cart must return 404, not an error page."""
    cart_id = new_cart()
    r = client.delete(f"/carts/{cart_id}/items/sticker")
    assert r.status_code == 404


def test_remove_item_twice_second_returns_404():
    """First DELETE removes the item; second DELETE on the same item returns 404."""
    cart_id = new_cart()
    client.post(f"/carts/{cart_id}/items", json={"product_id": "sticker", "quantity": 1})
    r1 = client.delete(f"/carts/{cart_id}/items/sticker")
    assert r1.status_code == 200
    r2 = client.delete(f"/carts/{cart_id}/items/sticker")
    assert r2.status_code == 404
