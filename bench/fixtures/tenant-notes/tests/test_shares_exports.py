from datetime import timedelta

from app.models import ShareLink, utcnow
from tests.conftest import as_user

OLIVIA = as_user("olivia")


def share(client, ws, note_id, **body):
    response = client.post(f"/workspaces/{ws}/notes/{note_id}/shares", json=body, headers=OLIVIA)
    assert response.status_code == 201
    return response.json()


def test_share_link_view_and_revoke(client, workspace, note):
    ws = workspace()
    n = note(ws, title="Launch", body="Tuesday")
    link = share(client, ws, n["id"])
    assert client.get(f"/s/{link['token']}").json()["title"] == "Launch"
    raw = client.get(f"/s/{link['token']}/raw")
    assert raw.text.startswith("# Launch")

    revoked = client.delete(f"/workspaces/{ws}/shares/{link['id']}", headers=OLIVIA).json()
    assert revoked["revoked_at"] is not None
    assert client.get(f"/s/{link['token']}").status_code == 404


def test_expired_link_is_gone(app, client, workspace, note):
    ws = workspace()
    n = note(ws)
    link = share(client, ws, n["id"], expires_in_hours=1)
    with app.state.sessionmaker() as session:
        session.get(ShareLink, link["id"]).expires_at = utcnow() - timedelta(minutes=1)
        session.commit()
    assert client.get(f"/s/{link['token']}").status_code == 404
    assert client.get(f"/s/{link['token']}/raw").status_code == 404


def test_deleted_note_link_is_gone(client, workspace, note):
    ws = workspace()
    n = note(ws)
    link = share(client, ws, n["id"])
    client.delete(f"/workspaces/{ws}/notes/{n['id']}", headers=OLIVIA)
    assert client.get(f"/s/{link['token']}").status_code == 404


def test_cannot_revoke_another_workspaces_link(client, workspace, note):
    ws = workspace()
    other = workspace(owner="tom")
    n = note(other, user="tom")
    link = client.post(f"/workspaces/{other}/notes/{n['id']}/shares", json={}, headers=as_user("tom")).json()
    assert client.delete(f"/workspaces/{ws}/shares/{link['id']}", headers=OLIVIA).status_code == 404


def test_export_whole_workspace(client, workspace, note):
    ws = workspace(name="Lab")
    note(ws, title="One")
    note(ws, title="Two")
    job = client.post(f"/workspaces/{ws}/exports", json={}, headers=OLIVIA).json()
    done = client.get(f"/workspaces/{ws}/exports/{job['id']}", headers=OLIVIA).json()
    assert (done["status"], done["note_count"]) == ("done", 2)
    text = client.get(f"/workspaces/{ws}/exports/{job['id']}/download", headers=OLIVIA).text
    assert "# One" in text and "# Two" in text


def test_export_selected_notes(client, workspace, note):
    ws = workspace()
    first = note(ws, title="Pick me")
    note(ws, title="Skip me")
    job = client.post(f"/workspaces/{ws}/exports", json={"note_ids": [first["id"]]}, headers=OLIVIA).json()
    text = client.get(f"/workspaces/{ws}/exports/{job['id']}/download", headers=OLIVIA).text
    assert "Pick me" in text and "Skip me" not in text


def test_finished_export_cannot_be_cancelled(client, workspace, note):
    ws = workspace()
    note(ws)
    job = client.post(f"/workspaces/{ws}/exports", json={}, headers=OLIVIA).json()
    assert client.delete(f"/workspaces/{ws}/exports/{job['id']}", headers=OLIVIA).status_code == 409
    second = client.post(f"/workspaces/{ws}/exports", json={}, headers=OLIVIA)
    assert second.status_code == 202


def test_export_is_private_to_its_workspace(client, workspace, note):
    ws = workspace()
    other = workspace(owner="tom")
    note(ws)
    job = client.post(f"/workspaces/{ws}/exports", json={}, headers=OLIVIA).json()
    tom_ws_job = client.get(f"/workspaces/{other}/exports/{job['id']}", headers=as_user("tom"))
    assert tom_ws_job.status_code == 404
