from datetime import timedelta

from app.models import utcnow
from app.services.orders import expire_unconfirmed_orders
from tests.conftest import STAFF, customer


def test_place_order_reserves_stock_and_authorizes(client, make_product, place):
    product = make_product(on_hand=5)
    response = place(product["id"], quantity=2)
    assert response.status_code == 201
    order = response.json()
    assert order["status"] == "placed"
    assert order["total_cents"] == 3000
    assert order["payment"]["status"] == "authorized"
    stock = client.get(f"/products/{product['id']}").json()
    assert stock["reserved"] == 2
    assert stock["available"] == 3


def test_out_of_stock_is_refused(client, make_product, place):
    product = make_product(on_hand=1)
    response = place(product["id"], quantity=2)
    assert response.status_code == 409
    assert response.json()["available"] == 1


def test_idempotency_key_replays_the_same_order(client, make_product, place):
    product = make_product(on_hand=5)
    first = place(product["id"], key="checkout-1").json()
    second = place(product["id"], key="checkout-1").json()
    assert first["id"] == second["id"]
    assert client.get(f"/products/{product['id']}").json()["reserved"] == 1


def test_declined_card_marks_payment_failed(make_product, place):
    product = make_product()
    order = place(product["id"], token="tok_decline").json()
    assert order["status"] == "payment_failed"
    assert order["payment"]["failure_reason"] == "decline"


def test_confirm_ship_deliver(client, make_product, place, gateway):
    product = make_product(on_hand=3)
    order_id = place(product["id"]).json()["id"]
    confirmed = client.post(f"/orders/{order_id}/confirm", headers=STAFF).json()
    assert confirmed["status"] == "confirmed"
    assert confirmed["payment"]["captured_cents"] == 1500

    shipped = client.post(
        f"/orders/{order_id}/ship", json={"carrier": "UPS", "tracking_number": "1Z999"}, headers=STAFF
    ).json()
    assert shipped["status"] == "shipped"
    stock = client.get(f"/products/{product['id']}").json()
    assert (stock["on_hand"], stock["reserved"]) == (2, 0)

    delivered = client.post("/warehouse/events", json={"order_id": order_id, "kind": "delivered"}, headers=STAFF)
    assert delivered.json()["status"] == "delivered"


def test_confirm_twice_captures_once(client, make_product, place, gateway):
    product = make_product()
    order_id = place(product["id"]).json()["id"]
    client.post(f"/orders/{order_id}/confirm", headers=STAFF)
    again = client.post(f"/orders/{order_id}/confirm", headers=STAFF)
    assert again.status_code == 200
    assert [c["captured"] for c in gateway.charges.values()] == [1500]


def test_cancel_placed_order_releases_stock_and_voids(client, make_product, place, gateway):
    product = make_product(on_hand=4)
    order_id = place(product["id"], quantity=3).json()["id"]
    cancelled = client.post(f"/orders/{order_id}/cancel", json={}, headers=customer("alice")).json()
    assert cancelled["status"] == "cancelled"
    assert cancelled["payment"]["status"] == "voided"
    assert client.get(f"/products/{product['id']}").json()["available"] == 4


def test_cancel_confirmed_order_refunds(client, make_product, place, gateway):
    product = make_product()
    order_id = place(product["id"]).json()["id"]
    client.post(f"/orders/{order_id}/confirm", headers=STAFF)
    cancelled = client.post(f"/orders/{order_id}/cancel", json={}, headers=customer("alice")).json()
    assert cancelled["payment"]["status"] == "refunded"
    assert gateway.refunds == [("ch_1", 1500)]


def test_cancel_delivered_order_is_refused(client, make_product, place):
    product = make_product()
    order_id = place(product["id"]).json()["id"]
    client.post(f"/orders/{order_id}/confirm", headers=STAFF)
    client.post(f"/orders/{order_id}/ship", json={"carrier": "UPS", "tracking_number": "1Z"}, headers=STAFF)
    client.post("/warehouse/events", json={"order_id": order_id, "kind": "delivered"}, headers=STAFF)
    response = client.post(f"/orders/{order_id}/cancel", json={}, headers=customer("alice"))
    assert response.status_code == 409


def test_other_customer_cannot_see_or_cancel(client, make_product, place):
    product = make_product()
    order_id = place(product["id"], who="alice").json()["id"]
    assert client.get(f"/orders/{order_id}", headers=customer("bob")).status_code == 404
    assert client.post(f"/orders/{order_id}/cancel", json={}, headers=customer("bob")).status_code == 404


def test_open_orders_filter(client, make_product, place):
    product = make_product()
    place(product["id"])
    second = place(product["id"]).json()["id"]
    client.post(f"/orders/{second}/cancel", json={}, headers=customer("alice"))
    open_orders = client.get("/orders?status=open", headers=customer("alice")).json()
    assert [o["status"] for o in open_orders] == ["placed"]


def test_sweeper_cancels_old_unconfirmed_orders(app, client, make_product, place, gateway):
    product = make_product(on_hand=2)
    place(product["id"])
    expired = expire_unconfirmed_orders(app.state.sessionmaker, gateway, now=utcnow() + timedelta(days=2))
    assert expired == 1
    assert client.get(f"/products/{product['id']}").json()["available"] == 2


def test_staff_routes_need_token(client, make_product, place):
    product = make_product()
    order_id = place(product["id"]).json()["id"]
    response = client.post(f"/orders/{order_id}/confirm", headers={"X-Staff-Token": "nope"})
    assert response.status_code == 403
