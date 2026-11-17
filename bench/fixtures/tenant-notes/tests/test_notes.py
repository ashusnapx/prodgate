from tests.conftest import as_user

OLIVIA = as_user("olivia")


def test_create_list_and_search(client, workspace, note):
    ws = workspace()
    note(ws, title="Quarterly plan")
    note(ws, title="Hiring", body="two engineers")
    titles = [n["title"] for n in client.get(f"/workspaces/{ws}/notes", headers=OLIVIA).json()]
    assert titles == ["Hiring", "Quarterly plan"]
    found = client.get(f"/workspaces/{ws}/notes?q=engineers", headers=OLIVIA).json()
    assert [n["title"] for n in found] == ["Hiring"]


def test_retried_create_returns_the_same_note(client, workspace, note):
    ws = workspace()
    first = note(ws, request_id="req-1")
    again = client.post(
        f"/workspaces/{ws}/notes", json={"title": "Plan", "request_id": "req-1"}, headers=OLIVIA
    )
    assert again.status_code == 200
    assert again.json()["id"] == first["id"]
    assert len(client.get(f"/workspaces/{ws}/notes", headers=OLIVIA).json()) == 1


def test_edit_bumps_version_and_rejects_stale_edit(client, workspace, note):
    ws = workspace()
    n = note(ws)
    edited = client.patch(f"/workspaces/{ws}/notes/{n['id']}", json={"base_version": 1, "body": "v2"}, headers=OLIVIA)
    assert edited.json()["version"] == 2
    stale = client.patch(f"/workspaces/{ws}/notes/{n['id']}", json={"base_version": 1, "body": "old"}, headers=OLIVIA)
    assert stale.status_code == 409
    assert client.get(f"/workspaces/{ws}/notes/{n['id']}", headers=OLIVIA).json()["body"] == "v2"


def test_members_and_roles(client, workspace, note):
    ws = workspace()
    n = note(ws)
    client.post(f"/workspaces/{ws}/members", json={"user_id": "victor", "role": "viewer"}, headers=OLIVIA)
    assert client.get(f"/workspaces/{ws}/notes/{n['id']}", headers=as_user("victor")).status_code == 200
    denied = client.patch(f"/workspaces/{ws}/notes/{n['id']}", json={"base_version": 1, "body": "x"}, headers=as_user("victor"))
    assert denied.status_code == 403
    assert client.get(f"/workspaces/{ws}/notes", headers=as_user("stranger")).status_code == 404


def test_note_from_another_workspace_is_hidden(client, workspace, note):
    mine = workspace(owner="olivia")
    theirs = workspace(owner="tom")
    secret = note(theirs, user="tom", title="Secret")
    assert client.get(f"/workspaces/{mine}/notes/{secret['id']}", headers=OLIVIA).status_code == 404


def test_delete_and_restore_note(client, workspace, note):
    ws = workspace()
    n = note(ws)
    assert client.delete(f"/workspaces/{ws}/notes/{n['id']}", headers=OLIVIA).status_code == 204
    assert client.get(f"/workspaces/{ws}/notes/{n['id']}", headers=OLIVIA).status_code == 404
    assert [t["id"] for t in client.get(f"/workspaces/{ws}/trash", headers=OLIVIA).json()] == [n["id"]]
    restored = client.post(f"/workspaces/{ws}/trash/{n['id']}/restore", headers=OLIVIA)
    assert restored.json()["deleted_at"] is None


def test_deleting_workspace_hides_it_and_restore_brings_notes_back(client, workspace, note):
    ws = workspace()
    keep = note(ws, title="Keep")
    trashed = note(ws, title="Trashed")
    client.delete(f"/workspaces/{ws}/notes/{trashed['id']}", headers=OLIVIA)
    assert client.delete(f"/workspaces/{ws}", headers=OLIVIA).status_code == 204
    assert client.get(f"/workspaces/{ws}/notes", headers=OLIVIA).status_code == 404
    assert client.get("/workspaces", headers=OLIVIA).json() == []

    assert client.post(f"/workspaces/{ws}/restore", headers=OLIVIA).status_code == 200
    live = [n["id"] for n in client.get(f"/workspaces/{ws}/notes", headers=OLIVIA).json()]
    assert live == [keep["id"]]
