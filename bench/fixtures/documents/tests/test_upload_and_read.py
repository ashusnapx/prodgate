from conftest import ORG, READER, deliver, report_error, upload


def test_upload_starts_a_reading(client, project, reader):
    up = upload(client)
    assert up["duplicate"] is False
    assert up["document"]["status"] == "processing"
    assert reader.submitted == [up["reading_id"]]

    deliver(client, up["reading_id"], pages=3)
    doc = client.get(f"/documents/{up['document']['id']}", headers=ORG).json()
    assert doc["status"] == "ready"
    current = client.get(f"/documents/{doc['id']}/reading", headers=ORG).json()
    assert current["page_count"] == 3
    assert current["is_current"] is True


def test_same_file_twice_returns_existing_document(client, project, reader):
    first = upload(client)
    second = upload(client, filename="copy-of-q3.txt")
    assert second["duplicate"] is True
    assert second["document"]["id"] == first["document"]["id"]
    assert len(reader.submitted) == 1


def test_rejects_empty_and_unsupported_files(client, project):
    empty = client.post("/projects/atlas/documents", params={"filename": "a.txt"}, content=b"", headers={**ORG, "Content-Type": "text/plain"})
    assert empty.status_code == 422
    exe = client.post("/projects/atlas/documents", params={"filename": "a.exe"}, content=b"MZ", headers={**ORG, "Content-Type": "application/x-msdownload"})
    assert exe.status_code == 422


def test_upload_to_unknown_project(client, project):
    resp = client.post("/projects/nope/documents", params={"filename": "a.txt"}, content=b"x", headers={**ORG, "Content-Type": "text/plain"})
    assert resp.status_code == 404


def test_reread_replaces_current_reading(client, project, reader):
    up = upload(client)
    doc_id = up["document"]["id"]
    deliver(client, up["reading_id"], text="first pass")

    rr = client.post(f"/documents/{doc_id}/reread", headers=ORG)
    assert rr.status_code == 202
    assert rr.json()["version"] == 2
    assert client.get(f"/documents/{doc_id}", headers=ORG).json()["status"] == "processing"

    deliver(client, rr.json()["id"], text="second pass")
    readings = client.get(f"/documents/{doc_id}/readings", headers=ORG).json()
    assert [(r["version"], r["state"], r["is_current"]) for r in readings] == [(1, "superseded", False), (2, "done", True)]
    assert client.get(f"/documents/{doc_id}/reading", headers=ORG).json()["text"] == "second pass"


def test_reread_while_reading_is_refused(client, project):
    up = upload(client)
    resp = client.post(f"/documents/{up['document']['id']}/reread", headers=ORG)
    assert resp.status_code == 409


def test_failed_first_reading_can_be_retried(client, project):
    up = upload(client)
    doc_id = up["document"]["id"]
    report_error(client, up["reading_id"])
    assert client.get(f"/documents/{doc_id}", headers=ORG).json()["status"] == "failed"

    rr = client.post(f"/documents/{doc_id}/reread", headers=ORG).json()
    deliver(client, rr["id"])
    assert client.get(f"/documents/{doc_id}", headers=ORG).json()["status"] == "ready"


def test_failed_reread_keeps_previous_reading(client, project):
    up = upload(client)
    doc_id = up["document"]["id"]
    deliver(client, up["reading_id"], text="good text")
    rr = client.post(f"/documents/{doc_id}/reread", headers=ORG).json()
    report_error(client, rr["id"])

    assert client.get(f"/documents/{doc_id}", headers=ORG).json()["status"] == "ready"
    assert client.get(f"/documents/{doc_id}/reading", headers=ORG).json()["text"] == "good text"


def test_repeated_result_callback_changes_nothing(client, project):
    up = upload(client)
    deliver(client, up["reading_id"], text="original")
    again = deliver(client, up["reading_id"], text="original")
    assert again["state"] == "done"
    assert len(client.get(f"/documents/{up['document']['id']}/readings", headers=ORG).json()) == 1


def test_reader_callbacks_need_token(client, project):
    up = upload(client)
    resp = client.post(f"/internal/readings/{up['reading_id']}/result", json={"text": "x"}, headers={"Authorization": "Bearer nope"})
    assert resp.status_code == 401


def test_unanswered_readings_expire(client, project, clock):
    up = upload(client)
    clock.advance(minutes=10)
    assert client.post("/internal/readings/expire", headers=READER).json() == {"expired": 0}
    clock.advance(minutes=25)
    assert client.post("/internal/readings/expire", headers=READER).json() == {"expired": 1}
    readings = client.get(f"/documents/{up['document']['id']}/readings", headers=ORG).json()
    assert readings[0]["state"] == "failed"


def test_search_finds_current_text(client, project):
    up = upload(client)
    deliver(client, up["reading_id"], text="The merger closes in March 2027.")
    hits = client.get("/projects/atlas/search", params={"q": "march"}, headers=ORG).json()
    assert [h["document_id"] for h in hits] == [up["document"]["id"]]
    assert "March 2027" in hits[0]["snippet"]
