from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app.clock import utcnow
from app.main import create_app
from app.services import users

ADMIN_EMAIL = "ada@acme.test"
ADMIN_PASSWORD = "correct horse battery"


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
    for module in ("app.services.sessions", "app.services.signin", "app.services.users"):
        monkeypatch.setattr(f"{module}.utcnow", fake)
    return fake


@pytest.fixture
def app(tmp_path, clock):
    app = create_app(f"sqlite:///{tmp_path / 'auth.db'}")
    with app.state.session_factory() as db:
        users.bootstrap_admin(db, "acme", ADMIN_EMAIL, "Ada", ADMIN_PASSWORD)
    return app


@pytest.fixture
def client(app):
    with TestClient(app) as c:
        yield c


def sign_in(client, email=ADMIN_EMAIL, password=ADMIN_PASSWORD, expect=200):
    resp = client.post("/auth/sign-in", json={"email": email, "password": password})
    assert resp.status_code == expect, resp.text
    return resp.json()


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def admin_token(client):
    return sign_in(client)["token"]


def invite(client, admin_token, email="bo@acme.test", role="member"):
    resp = client.post("/admin/invites", json={"email": email, "display_name": "Bo", "role": role}, headers=bearer(admin_token))
    assert resp.status_code == 201, resp.text
    return resp.json()


def join(client, admin_token, email="bo@acme.test", password="a long new password"):
    """Invite someone, sign them in with the one-time password and set their own."""
    inv = invite(client, admin_token, email)
    token = sign_in(client, email, inv["temporary_password"])["token"]
    resp = client.post("/me/password", json={"new_password": password}, headers=bearer(token))
    assert resp.status_code == 204, resp.text
    return inv["invite"]["user_id"], token
