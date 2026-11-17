import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.services.payments import FakeGateway

STAFF = {"X-Staff-Token": "staff-secret"}


def customer(customer_id: str) -> dict:
    return {"X-Customer-Id": customer_id}


@pytest.fixture
def gateway():
    return FakeGateway()


@pytest.fixture
def app(tmp_path, gateway):
    return create_app(f"sqlite:///{tmp_path / 'test.db'}", gateway=gateway, staff_token="staff-secret")


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def make_product(client):
    def make(sku="MUG-1", on_hand=10, price_cents=1500):
        response = client.post(
            "/products", json={"sku": sku, "name": sku.title(), "price_cents": price_cents, "on_hand": on_hand}, headers=STAFF
        )
        assert response.status_code == 201
        return response.json()

    return make


@pytest.fixture
def place(client):
    def place(product_id, quantity=1, who="alice", token="tok_visa", key=None):
        headers = customer(who)
        if key:
            headers["Idempotency-Key"] = key
        body = {"items": [{"product_id": product_id, "quantity": quantity}], "card_token": token}
        return client.post("/orders", json=body, headers=headers)

    return place
