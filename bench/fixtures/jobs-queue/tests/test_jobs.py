from conftest import TENANT, WORKER, claim, enqueue


def test_enqueue_and_fetch(client):
    job = enqueue(client)
    assert job["status"] == "queued"
    assert job["attempts"] == 0

    fetched = client.get(f"/jobs/{job['id']}", headers=TENANT).json()
    assert fetched["payload"] == {"to": "a@example.com"}


def test_idempotency_key_returns_original_job(client):
    first = enqueue(client, idempotency_key="order-42")
    resp = client.post("/jobs", json={"queue": "default", "kind": "email.send", "idempotency_key": "order-42"}, headers=TENANT)
    assert resp.status_code == 200
    assert resp.json()["id"] == first["id"]


def test_other_tenant_cannot_read_job(client):
    job = enqueue(client)
    resp = client.get(f"/jobs/{job['id']}", headers={"X-Tenant-Id": "globex"})
    assert resp.status_code == 404


def test_claim_complete_records_output(client):
    job = enqueue(client)
    claimed = claim(client)
    assert claimed["id"] == job["id"]
    assert claimed["status"] == "running"
    assert claimed["attempts"] == 1

    resp = client.post(f"/worker/jobs/{job['id']}/complete", json={"worker_id": "w1", "output": {"sent": True}}, headers=WORKER)
    assert resp.status_code == 200
    assert resp.json()["status"] == "succeeded"

    outputs = client.get(f"/jobs/{job['id']}/outputs", headers=TENANT).json()
    assert [o["data"] for o in outputs] == [{"sent": True}]


def test_claim_respects_priority_and_empty_queue(client):
    low = enqueue(client, priority=0)
    high = enqueue(client, priority=10)
    assert claim(client)["id"] == high["id"]
    assert claim(client)["id"] == low["id"]
    assert claim(client) is None


def test_worker_routes_need_token(client):
    resp = client.post("/worker/claim", json={"queue": "default", "worker_id": "w1"}, headers={"X-Worker-Token": "nope"})
    assert resp.status_code == 401


def test_heartbeat_from_other_worker_is_rejected(client):
    job = enqueue(client)
    claim(client, worker="w1")
    ok = client.post(f"/worker/jobs/{job['id']}/heartbeat", json={"worker_id": "w1"}, headers=WORKER)
    assert ok.status_code == 204
    other = client.post(f"/worker/jobs/{job['id']}/heartbeat", json={"worker_id": "w2"}, headers=WORKER)
    assert other.status_code == 409


def test_failure_is_retried_with_backoff(client, clock):
    job = enqueue(client, max_attempts=3)
    claim(client)
    resp = client.post(f"/worker/jobs/{job['id']}/fail", json={"worker_id": "w1", "error": "smtp timeout"}, headers=WORKER)
    body = resp.json()
    assert body["status"] == "queued"
    assert body["last_error"] == "smtp timeout"

    assert claim(client) is None
    clock.advance(11)
    assert claim(client)["attempts"] == 2


def test_failure_after_last_attempt_dead_letters(client, clock):
    job = enqueue(client, max_attempts=1)
    claim(client)
    resp = client.post(f"/worker/jobs/{job['id']}/fail", json={"worker_id": "w1", "error": "boom"}, headers=WORKER)
    assert resp.json()["status"] == "dead"


def test_non_retryable_failure_dead_letters(client):
    job = enqueue(client, max_attempts=5)
    claim(client)
    resp = client.post(f"/worker/jobs/{job['id']}/fail", json={"worker_id": "w1", "error": "bad payload", "retryable": False}, headers=WORKER)
    assert resp.json()["status"] == "dead"


def test_cancel_queued_job(client):
    job = enqueue(client)
    resp = client.post(f"/jobs/{job['id']}/cancel", json={"reason": "user asked"}, headers=TENANT)
    assert resp.json()["status"] == "canceled"
    assert claim(client) is None
    again = client.post(f"/jobs/{job['id']}/cancel", headers=TENANT)
    assert again.status_code == 409


def test_complete_after_cancel_is_rejected(client):
    job = enqueue(client)
    claim(client)
    client.post(f"/jobs/{job['id']}/cancel", headers=TENANT)
    resp = client.post(f"/worker/jobs/{job['id']}/complete", json={"worker_id": "w1"}, headers=WORKER)
    assert resp.status_code == 409


def test_retry_dead_job(client):
    job = enqueue(client, max_attempts=1)
    claim(client)
    client.post(f"/worker/jobs/{job['id']}/fail", json={"worker_id": "w1", "error": "boom"}, headers=WORKER)
    resp = client.post(f"/jobs/{job['id']}/retry", headers=TENANT)
    assert resp.json()["status"] == "queued"
    assert resp.json()["attempts"] == 0
    assert claim(client)["id"] == job["id"]


def test_retry_running_job_is_rejected(client):
    job = enqueue(client)
    claim(client)
    assert client.post(f"/jobs/{job['id']}/retry", headers=TENANT).status_code == 409


def test_list_jobs_by_status(client):
    enqueue(client)
    second = enqueue(client)
    client.post(f"/jobs/{second['id']}/cancel", headers=TENANT)
    canceled = client.get("/jobs", params={"status": "canceled"}, headers=TENANT).json()
    assert [j["id"] for j in canceled] == [second["id"]]
