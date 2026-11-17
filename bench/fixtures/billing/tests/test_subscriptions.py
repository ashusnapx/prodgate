from conftest import ACCOUNT, invoices_of, run_cycle, subscribe


def test_subscribe_charges_first_period(client, provider):
    sub = subscribe(client)
    assert sub["status"] == "active"
    [invoice] = invoices_of(client, sub["id"])
    assert invoice["status"] == "paid"
    assert invoice["amount_paid_cents"] == 1000
    assert len(provider.charges) == 1


def test_trial_converts_to_paid_period(client, clock):
    sub = subscribe(client, "team-trial")
    assert sub["status"] == "trialing"
    assert invoices_of(client, sub["id"]) == []

    clock.advance(days=14, minutes=1)
    result = run_cycle(client)
    assert result["trials_ended"] == [sub["id"]]
    after = client.get(f"/subscriptions/{sub['id']}", headers=ACCOUNT).json()
    assert after["status"] == "active"
    [invoice] = invoices_of(client, sub["id"])
    assert (invoice["amount_cents"], invoice["status"]) == (5000, "paid")


def test_renewal_bills_next_period(client, clock):
    sub = subscribe(client)
    clock.advance(days=30, minutes=1)
    result = run_cycle(client)
    assert result["renewed"] == [sub["id"]]
    assert [i["status"] for i in invoices_of(client, sub["id"])] == ["paid", "paid"]
    assert run_cycle(client)["renewed"] == []


def test_cancel_at_period_end(client, clock):
    sub = subscribe(client)
    resp = client.post(f"/subscriptions/{sub['id']}/cancel", json={"at_period_end": True}, headers=ACCOUNT)
    assert resp.json()["cancel_at_period_end"] is True
    assert resp.json()["status"] == "active"

    clock.advance(days=31)
    run_cycle(client)
    assert client.get(f"/subscriptions/{sub['id']}", headers=ACCOUNT).json()["status"] == "canceled"
    assert len(invoices_of(client, sub["id"])) == 1


def test_cancel_now_voids_unpaid_invoices(client, provider):
    provider.outcome = "failed"
    sub = subscribe(client)
    assert client.get(f"/subscriptions/{sub['id']}", headers=ACCOUNT).json()["status"] == "past_due"

    resp = client.post(f"/subscriptions/{sub['id']}/cancel", json={"at_period_end": False}, headers=ACCOUNT)
    assert resp.json()["status"] == "canceled"
    assert [i["status"] for i in invoices_of(client, sub["id"])] == ["void"]
    again = client.post(f"/subscriptions/{sub['id']}/cancel", json={"at_period_end": False}, headers=ACCOUNT)
    assert again.status_code == 409


def test_upgrade_mid_period_charges_proration_once(client, clock, provider):
    sub = subscribe(client)
    clock.advance(days=15)
    body = {"plan_code": "pro", "request_id": "chg-0001-abcd"}
    first = client.post(f"/subscriptions/{sub['id']}/change-plan", json=body, headers=ACCOUNT).json()
    proration = first["proration_invoice"]
    assert proration["amount_cents"] == 1000
    assert proration["status"] == "paid"

    again = client.post(f"/subscriptions/{sub['id']}/change-plan", json=body, headers=ACCOUNT).json()
    assert again["proration_invoice"]["id"] == proration["id"]
    assert len(provider.charges) == 2


def test_downgrade_switches_plan_without_charge(client, clock, provider):
    sub = subscribe(client, "pro")
    clock.advance(days=10)
    resp = client.post(f"/subscriptions/{sub['id']}/change-plan", json={"plan_code": "basic", "request_id": "chg-0002-abcd"}, headers=ACCOUNT)
    assert resp.json()["proration_invoice"] is None
    assert resp.json()["subscription"]["plan_id"] != sub["plan_id"]
    assert len(provider.charges) == 1


def test_change_to_current_plan_is_refused(client):
    sub = subscribe(client)
    resp = client.post(f"/subscriptions/{sub['id']}/change-plan", json={"plan_code": "basic", "request_id": "chg-0003-abcd"}, headers=ACCOUNT)
    assert resp.status_code == 409


def test_other_account_cannot_see_subscription(client):
    sub = subscribe(client)
    assert client.get(f"/subscriptions/{sub['id']}", headers={"X-Account-Id": "acct_other"}).status_code == 404
