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


def test_duplicate_discount_code_rejected():
    """The same discount code may only be applied once per cart.

    Applying SAVE10 twice must return 409 on the second call and must
    not double the discount.
    """
    cart_id = new_cart()
    client.post(f"/carts/{cart_id}/items", json={"product_id": "tshirt", "quantity": 2})
    # First application should succeed
    r1 = client.post(f"/carts/{cart_id}/discount", json={"code": "SAVE10"})
    assert r1.status_code == 200
    # Second application of the same code must be rejected
    r2 = client.post(f"/carts/{cart_id}/discount", json={"code": "SAVE10"})
    assert r2.status_code == 409
