import pytest
from fastapi.testclient import TestClient

from app.main import app, reset_store

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_store():
    reset_store()
    yield
    reset_store()


def new_cart() -> int:
    response = client.post("/carts")
    assert response.status_code == 201
    return response.json()["id"]


def test_list_products():
    response = client.get("/products")
    assert response.status_code == 200
    ids = {p["id"] for p in response.json()}
    assert ids == {"mug", "tshirt", "sticker"}


def test_new_cart_is_empty():
    cart_id = new_cart()
    cart = client.get(f"/carts/{cart_id}").json()
    assert cart["items"] == []
    assert cart["total"] == "0.00"


def test_add_item_updates_total():
    cart_id = new_cart()
    response = client.post(
        f"/carts/{cart_id}/items", json={"product_id": "mug", "quantity": 2}
    )
    assert response.status_code == 200
    assert response.json()["total"] == "25.00"


def test_adding_same_product_twice_adds_quantities():
    cart_id = new_cart()
    client.post(f"/carts/{cart_id}/items", json={"product_id": "sticker", "quantity": 1})
    cart = client.post(
        f"/carts/{cart_id}/items", json={"product_id": "sticker", "quantity": 2}
    ).json()
    assert cart["items"][0]["quantity"] == 3
    assert cart["total"] == "12.00"


def test_unknown_product_is_404():
    cart_id = new_cart()
    response = client.post(
        f"/carts/{cart_id}/items", json={"product_id": "laptop", "quantity": 1}
    )
    assert response.status_code == 404


def test_update_quantity():
    cart_id = new_cart()
    client.post(f"/carts/{cart_id}/items", json={"product_id": "mug", "quantity": 1})
    cart = client.patch(f"/carts/{cart_id}/items/mug", json={"quantity": 3}).json()
    assert cart["total"] == "37.50"


def test_update_quantity_below_one_is_rejected():
    cart_id = new_cart()
    client.post(f"/carts/{cart_id}/items", json={"product_id": "mug", "quantity": 1})
    response = client.patch(f"/carts/{cart_id}/items/mug", json={"quantity": 0})
    assert response.status_code == 422


def test_remove_item():
    cart_id = new_cart()
    client.post(f"/carts/{cart_id}/items", json={"product_id": "mug", "quantity": 1})
    cart = client.delete(f"/carts/{cart_id}/items/mug").json()
    assert cart["items"] == []


def test_discount_code():
    cart_id = new_cart()
    client.post(f"/carts/{cart_id}/items", json={"product_id": "tshirt", "quantity": 4})
    cart = client.post(f"/carts/{cart_id}/discount", json={"code": "save10"}).json()
    assert cart["discounts"] == ["SAVE10"]
    assert cart["total"] == "90.00"


def test_unknown_discount_code_is_404():
    cart_id = new_cart()
    response = client.post(f"/carts/{cart_id}/discount", json={"code": "FREE"})
    assert response.status_code == 404
