from app.services import jobs
from app.worker import PermanentError, Worker
from conftest import TENANT, WORKER, claim, enqueue


def make_batch(client, n=2, callback_url="https://example.com/hook"):
    body = {
        "name": "nightly export",
        "callback_url": callback_url,
        "jobs": [{"queue": "export", "kind": "export.part", "payload": {"part": i}} for i in range(n)],
    }
    resp = client.post("/batches", json=body, headers=TENANT)
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_batch_completes_when_all_jobs_succeed(client, session_factory):
    batch = make_batch(client, n=3)
    worker = Worker(session_factory, "export", "w1", {"export.part": lambda payload, beat: {"rows": payload["part"] * 10}})
    assert len(worker.run_until_empty()) == 3

    done = client.get(f"/batches/{batch['id']}", headers=TENANT).json()
    assert done["status"] == "completed"
    assert done["counts"] == {"succeeded": 3}

    callbacks = client.get("/jobs", params={"status": "queued"}, headers=TENANT).json()
    assert [j["kind"] for j in callbacks] == ["batch.callback"]
    assert callbacks[0]["payload"]["status"] == "completed"


def test_batch_with_dead_job_completes_with_errors(client, session_factory):
    batch = make_batch(client, n=2, callback_url=None)

    def handler(payload, beat):
        if payload["part"] == 1:
            raise PermanentError("part 1 is corrupt")
        return {"ok": True}

    Worker(session_factory, "export", "w1", {"export.part": handler}).run_until_empty()
    done = client.get(f"/batches/{batch['id']}", headers=TENANT).json()
    assert done["status"] == "completed_with_errors"
    assert done["counts"] == {"succeeded": 1, "dead": 1}


def test_batch_stays_open_while_jobs_run(client):
    batch = make_batch(client, n=2)
    first = claim(client, queue="export")
    client.post(f"/worker/jobs/{first['id']}/complete", json={"worker_id": "w1"}, headers=WORKER)
    assert client.get(f"/batches/{batch['id']}", headers=TENANT).json()["status"] == "open"


def test_worker_retries_transient_errors(client, session_factory, clock):
    enqueue(client, kind="flaky", max_attempts=2)
    calls = []

    def flaky(payload, beat):
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("connection reset")
        beat()
        return {"ok": True}

    worker = Worker(session_factory, "default", "w1", {"flaky": flaky})
    worker.run_once()
    clock.advance(30)
    job_id = worker.run_once()
    with session_factory() as db:
        assert jobs.get_job(db, job_id).status.value == "succeeded"


def test_silent_worker_is_recovered(client, clock):
    job = enqueue(client, max_attempts=3)
    claim(client, worker="w1")
    client.post(f"/worker/jobs/{job['id']}/heartbeat", json={"worker_id": "w1"}, headers=WORKER)

    clock.advance(60)
    assert client.post("/worker/recover", headers=WORKER).json() == {"recovered": []}

    clock.advance(60)
    assert client.post("/worker/recover", headers=WORKER).json() == {"recovered": [job["id"]]}
    recovered = client.get(f"/jobs/{job['id']}", headers=TENANT).json()
    assert recovered["status"] == "queued"
    assert recovered["lease_owner"] is None

    late = client.post(f"/worker/jobs/{job['id']}/heartbeat", json={"worker_id": "w1"}, headers=WORKER)
    assert late.status_code == 409


def test_recovery_dead_letters_last_attempt(client, clock):
    job = enqueue(client, max_attempts=1)
    claim(client)
    client.post(f"/worker/jobs/{job['id']}/heartbeat", json={"worker_id": "w1"}, headers=WORKER)
    clock.advance(120)
    client.post("/worker/recover", headers=WORKER)
    assert client.get(f"/jobs/{job['id']}", headers=TENANT).json()["status"] == "dead"
