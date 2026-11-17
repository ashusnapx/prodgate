from conftest import ACCOUNT, invoices_of, run_cycle, send_webhook, subscribe


def pending_subscription(client, provider):
    provider.outcome = "processing"
    sub = subscribe(client)
    [invoice] = invoices_of(client, sub["id"])
    assert invoice["status"] == "pending"
    return sub, invoice, next(iter(provider.charges))


def test_webhook_settles_processing_charge(client, provider):
    sub, invoice, charge_id = pending_subscription(client, provider)
    assert send_webhook(client, "payment.succeeded", invoice, charge_id, event_id="evt_a") == "processed"
    [paid] = invoices_of(client, sub["id"])
    assert (paid["status"], paid["amount_paid_cents"]) == ("paid", 1000)


def test_repeated_webhook_is_ignored(client, provider):
    sub, invoice, charge_id = pending_subscription(client, provider)
    send_webhook(client, "payment.succeeded", invoice, charge_id, event_id="evt_b")
    assert send_webhook(client, "payment.succeeded", invoice, charge_id, event_id="evt_b") == "duplicate"
    assert invoices_of(client, sub["id"])[0]["amount_paid_cents"] == 1000


def test_failed_payment_then_retry_from_dashboard(client, provider):
    sub, invoice, charge_id = pending_subscription(client, provider)
    send_webhook(client, "payment.failed", invoice, charge_id, failure_reason="insufficient_funds")
    assert client.get(f"/subscriptions/{sub['id']}", headers=ACCOUNT).json()["status"] == "past_due"
    assert invoices_of(client, sub["id"])[0]["failure_reason"] == "insufficient_funds"

    provider.outcome = "succeeded"
    resp = client.post(f"/invoices/{invoice['id']}/pay", headers=ACCOUNT)
    assert resp.json()["status"] == "paid"
    assert client.get(f"/subscriptions/{sub['id']}", headers=ACCOUNT).json()["status"] == "active"


def test_paying_a_paid_invoice_is_refused(client):
    sub = subscribe(client)
    invoice = invoices_of(client, sub["id"])[0]
    assert client.post(f"/invoices/{invoice['id']}/pay", headers=ACCOUNT).status_code == 409


def test_provider_outage_on_pay(client, provider):
    provider.outcome = "failed"
    sub = subscribe(client)
    invoice = invoices_of(client, sub["id"])[0]
    provider.unreachable = True
    assert client.post(f"/invoices/{invoice['id']}/pay", headers=ACCOUNT).status_code == 502


def test_reconcile_settles_charge_without_webhook(client, provider, clock):
    sub, invoice, charge_id = pending_subscription(client, provider)
    assert run_cycle(client)["reconciled"] == []
    provider.charges[charge_id].status = "succeeded"
    clock.advance(hours=2)
    assert run_cycle(client)["reconciled"] == [invoice["id"]]
    assert invoices_of(client, sub["id"])[0]["status"] == "paid"


def test_webhook_needs_valid_signature(client):
    resp = client.post("/webhooks/provider", content=b'{"id": "evt_x"}', headers={"X-Signature": "sha256=bad"})
    assert resp.status_code == 401


def test_partial_refund_and_idempotent_retry(client, provider):
    sub = subscribe(client)
    invoice = invoices_of(client, sub["id"])[0]
    headers = {**ACCOUNT, "Idempotency-Key": "refund-0001"}
    first = client.post(f"/invoices/{invoice['id']}/refunds", json={"amount_cents": 400}, headers=headers)
    assert first.status_code == 201
    again = client.post(f"/invoices/{invoice['id']}/refunds", json={"amount_cents": 400}, headers=headers)
    assert again.json()["id"] == first.json()["id"]
    assert len(provider.refunds) == 1
    assert client.get(f"/invoices/{invoice['id']}", headers=ACCOUNT).json()["amount_refunded_cents"] == 400


def test_refund_cannot_exceed_payment(client):
    sub = subscribe(client)
    invoice = invoices_of(client, sub["id"])[0]
    resp = client.post(f"/invoices/{invoice['id']}/refunds", json={"amount_cents": 1001}, headers={**ACCOUNT, "Idempotency-Key": "refund-0002"})
    assert resp.status_code == 409


def test_other_account_cannot_refund(client):
    sub = subscribe(client)
    invoice = invoices_of(client, sub["id"])[0]
    resp = client.post(f"/invoices/{invoice['id']}/refunds", json={"amount_cents": 100}, headers={"X-Account-Id": "acct_other", "Idempotency-Key": "refund-0003"})
    assert resp.status_code == 404
