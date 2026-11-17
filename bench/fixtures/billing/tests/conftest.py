import hashlib
import hmac
import itertools
import json
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app.clock import utcnow
from app.config import settings
from app.main import create_app
from app.provider import FakeProvider

ACCOUNT = {"X-Account-Id": "acct_sunrise"}
CRON = {"X-Cron-Token": settings.cron_token}
_event_ids = itertools.count(1)


class FakeClock:
    def __init__(self):
        self.now = utcnow()

    def __call__(self):
        return self.now

    def advance(self, **kwargs) -> None:
        self.now += timedelta(**kwargs)


@pytest.fixture
def clock(monkeypatch):
    fake = FakeClock()
    for module in ("app.services.invoices", "app.services.subscriptions", "app.services.cycle"):
        monkeypatch.setattr(f"{module}.utcnow", fake)
    return fake


@pytest.fixture
def provider():
    return FakeProvider()


@pytest.fixture
def client(tmp_path, clock, provider):
    app = create_app(f"sqlite:///{tmp_path / 'billing.db'}", provider=provider)
    with TestClient(app) as c:
        for plan in (
            {"code": "basic", "name": "Basic", "price_cents": 1000},
            {"code": "pro", "name": "Pro", "price_cents": 3000},
            {"code": "team-trial", "name": "Team", "price_cents": 5000, "trial_days": 14},
        ):
            assert c.post("/plans", json=plan, headers=ACCOUNT).status_code == 201
        yield c


def subscribe(client, plan_code="basic", customer="cus_123"):
    resp = client.post("/subscriptions", json={"customer_ref": customer, "plan_code": plan_code}, headers=ACCOUNT)
    assert resp.status_code == 201, resp.text
    return resp.json()


def invoices_of(client, sub_id):
    return client.get(f"/subscriptions/{sub_id}/invoices", headers=ACCOUNT).json()


def send_webhook(client, event_type, invoice, charge_id, event_id=None, **data):
    event = {
        "id": event_id or f"evt_{next(_event_ids)}",
        "type": event_type,
        "data": {"charge_id": charge_id, "amount_cents": invoice["amount_cents"], "metadata": {"invoice_id": invoice["id"]}, **data},
    }
    body = json.dumps(event).encode()
    signature = "sha256=" + hmac.new(settings.webhook_secret.encode(), body, hashlib.sha256).hexdigest()
    resp = client.post("/webhooks/provider", content=body, headers={"X-Signature": signature, "Content-Type": "application/json"})
    assert resp.status_code == 200, resp.text
    return resp.json()["result"]


def run_cycle(client):
    resp = client.post("/jobs/billing-cycle", headers=CRON)
    assert resp.status_code == 200, resp.text
    return resp.json()
