import pytest
from fastapi.testclient import TestClient

from app.main import create_app


def as_user(user_id: str) -> dict:
    return {"X-User-Id": user_id}


@pytest.fixture
def app(tmp_path):
    return create_app(f"sqlite:///{tmp_path / 'notes.db'}")


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def workspace(client):
    def make(owner="olivia", name="Research"):
        response = client.post("/workspaces", json={"name": name}, headers=as_user(owner))
        assert response.status_code == 201
        return response.json()["id"]

    return make


@pytest.fixture
def note(client):
    def make(workspace_id, user="olivia", title="Plan", body="first draft", request_id=None):
        payload = {"title": title, "body": body, "request_id": request_id}
        response = client.post(f"/workspaces/{workspace_id}/notes", json=payload, headers=as_user(user))
        assert response.status_code in (200, 201)
        return response.json()

    return make
