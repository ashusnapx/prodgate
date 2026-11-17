from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app.clock import utcnow
from app.config import settings
from app.main import create_app

WORKER = {"X-Worker-Token": settings.worker_token}
TENANT = {"X-Tenant-Id": "acme"}


class FakeClock:
    def __init__(self):
        self.now = utcnow()

    def __call__(self):
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


@pytest.fixture
def clock(monkeypatch):
    fake = FakeClock()
    for module in ("app.services.jobs", "app.services.batches", "app.services.recovery"):
        monkeypatch.setattr(f"{module}.utcnow", fake)
    return fake


@pytest.fixture
def app(tmp_path, clock):
    return create_app(f"sqlite:///{tmp_path / 'jobs.db'}")


@pytest.fixture
def client(app):
    with TestClient(app) as c:
        yield c


@pytest.fixture
def session_factory(app):
    return app.state.session_factory


def enqueue(client, **overrides):
    body = {"queue": "default", "kind": "email.send", "payload": {"to": "a@example.com"}, **overrides}
    resp = client.post("/jobs", json=body, headers=TENANT)
    assert resp.status_code in (200, 201), resp.text
    return resp.json()


def claim(client, worker="w1", queue="default"):
    resp = client.post("/worker/claim", json={"queue": queue, "worker_id": worker}, headers=WORKER)
    return None if resp.status_code == 204 else resp.json()
