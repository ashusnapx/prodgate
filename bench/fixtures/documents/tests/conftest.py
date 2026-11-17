from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app.clock import utcnow
from app.config import settings
from app.main import create_app
from app.reader_client import RecordingReader

ORG = {"X-Org-Id": "northwind", "X-User-Id": "dana"}
READER = {"Authorization": f"Bearer {settings.reader_token}"}


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
    for module in ("app.services.documents", "app.services.readings"):
        monkeypatch.setattr(f"{module}.utcnow", fake)
    return fake


@pytest.fixture
def reader():
    return RecordingReader()


@pytest.fixture
def client(tmp_path, clock, reader):
    app = create_app(f"sqlite:///{tmp_path / 'docs.db'}", reader=reader)
    with TestClient(app) as c:
        yield c


@pytest.fixture
def project(client):
    resp = client.post("/projects", json={"code": "atlas", "name": "Atlas"}, headers=ORG)
    assert resp.status_code == 201, resp.text
    return resp.json()


def upload(client, data=b"Quarterly revenue grew 12 percent.", filename="q3.txt", code="atlas", content_type="text/plain", headers=ORG):
    resp = client.post(
        f"/projects/{code}/documents",
        params={"filename": filename},
        content=data,
        headers={**headers, "Content-Type": content_type},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def deliver(client, reading_id, text="Quarterly revenue grew 12 percent.", pages=1):
    resp = client.post(f"/internal/readings/{reading_id}/result", json={"text": text, "page_count": pages}, headers=READER)
    assert resp.status_code == 200, resp.text
    return resp.json()


def report_error(client, reading_id, error="could not parse"):
    resp = client.post(f"/internal/readings/{reading_id}/error", json={"error": error}, headers=READER)
    assert resp.status_code == 200, resp.text
    return resp.json()
