from conftest import ORG, deliver, upload

OTHER_ORG = {"X-Org-Id": "contoso", "X-User-Id": "eve"}


def ready_doc(client, data=b"Board minutes, 4 June.", text="Board minutes, 4 June."):
    up = upload(client, data=data)
    deliver(client, up["reading_id"], text=text)
    return up["document"]["id"]


def test_withdraw_hides_document(client, project):
    doc_id = ready_doc(client)
    resp = client.post(f"/documents/{doc_id}/withdraw", headers=ORG)
    assert resp.json()["status"] == "withdrawn"

    assert client.get("/projects/atlas/documents", headers=ORG).json() == []
    listed = client.get("/projects/atlas/documents", params={"include_withdrawn": True}, headers=ORG).json()
    assert [d["id"] for d in listed] == [doc_id]
    assert client.get("/projects/atlas/search", params={"q": "board"}, headers=ORG).json() == []
    assert client.get(f"/documents/{doc_id}/content", headers=ORG).status_code == 404
    assert client.get(f"/documents/{doc_id}/reading", headers=ORG).status_code == 404


def test_restore_brings_document_back(client, project):
    doc_id = ready_doc(client)
    client.post(f"/documents/{doc_id}/withdraw", headers=ORG)
    resp = client.post(f"/documents/{doc_id}/restore", headers=ORG)
    assert resp.json()["status"] == "ready"
    assert client.get(f"/documents/{doc_id}/content", headers=ORG).content == b"Board minutes, 4 June."
    assert len(client.get("/projects/atlas/search", params={"q": "board"}, headers=ORG).json()) == 1


def test_withdraw_twice_and_restore_live_are_refused(client, project):
    doc_id = ready_doc(client)
    assert client.post(f"/documents/{doc_id}/restore", headers=ORG).status_code == 409
    client.post(f"/documents/{doc_id}/withdraw", headers=ORG)
    assert client.post(f"/documents/{doc_id}/withdraw", headers=ORG).status_code == 409


def test_reread_of_withdrawn_document_is_refused(client, project):
    doc_id = ready_doc(client)
    client.post(f"/documents/{doc_id}/withdraw", headers=ORG)
    assert client.post(f"/documents/{doc_id}/reread", headers=ORG).status_code == 409


def test_withdrawn_copy_does_not_block_new_upload(client, project):
    doc_id = ready_doc(client)
    client.post(f"/documents/{doc_id}/withdraw", headers=ORG)
    again = upload(client, data=b"Board minutes, 4 June.")
    assert again["duplicate"] is False
    assert again["document"]["id"] != doc_id


def test_rename_moves_documents(client, project):
    doc_id = ready_doc(client)
    resp = client.patch("/projects/atlas", json={"code": "atlas-2027", "name": "Atlas 2027"}, headers=ORG)
    assert resp.status_code == 200
    assert client.get("/projects/atlas/documents", headers=ORG).status_code == 404
    docs = client.get("/projects/atlas-2027/documents", headers=ORG).json()
    assert [d["id"] for d in docs] == [doc_id]
    assert docs[0]["project_code"] == "atlas-2027"
    assert len(client.get("/projects/atlas-2027/search", params={"q": "board"}, headers=ORG).json()) == 1


def test_rename_to_taken_code(client, project):
    client.post("/projects", json={"code": "zephyr", "name": "Zephyr"}, headers=ORG)
    resp = client.patch("/projects/atlas", json={"code": "zephyr", "name": "Atlas"}, headers=ORG)
    assert resp.status_code == 409


def test_other_org_cannot_see_or_change_documents(client, project):
    doc_id = ready_doc(client)
    assert client.get(f"/documents/{doc_id}", headers=OTHER_ORG).status_code == 404
    assert client.get(f"/documents/{doc_id}/readings", headers=OTHER_ORG).status_code == 404
    assert client.post(f"/documents/{doc_id}/withdraw", headers=OTHER_ORG).status_code == 404
    assert client.get("/projects/atlas/documents", headers=OTHER_ORG).status_code == 404
