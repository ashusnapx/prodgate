from tests.conftest import STAFF, customer


def deliver(client, order_id):
    client.post(f"/orders/{order_id}/confirm", headers=STAFF)
    client.post(f"/orders/{order_id}/ship", json={"carrier": "DHL", "tracking_number": "JD01"}, headers=STAFF)
    client.post("/warehouse/events", json={"order_id": order_id, "kind": "delivered"}, headers=STAFF)


def test_return_approved_refunds_and_restocks(client, make_product, place, gateway):
    product = make_product(on_hand=5)
    order = place(product["id"], quantity=3).json()
    deliver(client, order["id"])
    line_id = order["lines"][0]["id"]

    created = client.post(
        f"/orders/{order['id']}/returns",
        json={"items": [{"order_line_id": line_id, "quantity": 2}], "reason": "too big"},
        headers=customer("alice"),
    )
    assert created.status_code == 201
    assert created.json()["refund_cents"] == 3000

    approved = client.post(f"/returns/{created.json()['id']}/approve", headers=STAFF).json()
    assert approved["status"] == "approved"
    assert gateway.refunds == [("ch_1", 3000)]
    assert client.get(f"/products/{product['id']}").json()["on_hand"] == 4


def test_cannot_return_more_than_bought(client, make_product, place):
    product = make_product()
    order = place(product["id"], quantity=1).json()
    deliver(client, order["id"])
    body = {"items": [{"order_line_id": order["lines"][0]["id"], "quantity": 2}], "reason": "x"}
    assert client.post(f"/orders/{order['id']}/returns", json=body, headers=customer("alice")).status_code == 409


def test_cannot_return_undelivered_order(client, make_product, place):
    product = make_product()
    order = place(product["id"]).json()
    body = {"items": [{"order_line_id": order["lines"][0]["id"], "quantity": 1}], "reason": "x"}
    assert client.post(f"/orders/{order['id']}/returns", json=body, headers=customer("alice")).status_code == 409


def test_rejected_return_cannot_be_approved(client, make_product, place, gateway):
    product = make_product()
    order = place(product["id"]).json()
    deliver(client, order["id"])
    body = {"items": [{"order_line_id": order["lines"][0]["id"], "quantity": 1}], "reason": "x"}
    return_id = client.post(f"/orders/{order['id']}/returns", json=body, headers=customer("alice")).json()["id"]
    rejected = client.post(f"/returns/{return_id}/reject", json={"note": "used"}, headers=STAFF).json()
    assert rejected["status"] == "rejected"
    assert client.post(f"/returns/{return_id}/approve", headers=STAFF).status_code == 409
    assert gateway.refunds == []


def test_return_is_private_to_its_customer(client, make_product, place):
    product = make_product()
    order = place(product["id"]).json()
    deliver(client, order["id"])
    body = {"items": [{"order_line_id": order["lines"][0]["id"], "quantity": 1}], "reason": "x"}
    return_id = client.post(f"/orders/{order['id']}/returns", json=body, headers=customer("alice")).json()["id"]
    assert client.get(f"/returns/{return_id}", headers=customer("bob")).status_code == 404
    assert client.get(f"/returns/{return_id}", headers=customer("alice")).status_code == 200
