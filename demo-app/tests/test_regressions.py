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


def test_add_item_negative_quantity_is_rejected():
    """POST /carts/{id}/items with quantity -3 must be rejected with 422."""
    cart_id = new_cart()
    response = client.post(
        f"/carts/{cart_id}/items", json={"product_id": "mug", "quantity": -3}
    )
    assert response.status_code == 422
