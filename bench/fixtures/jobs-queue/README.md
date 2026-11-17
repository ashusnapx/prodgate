# jobs-queue

A small background job queue served over HTTP. Tenants put jobs on named queues; workers claim jobs, run them and report back. Built with FastAPI and SQLAlchemy on SQLite.

## Concepts

- **Job**: a unit of work with a `queue`, a `kind` (which handler runs it), a JSON `payload`, a `priority` and an attempt budget (`max_attempts`, default 5).
- **Status**: `queued` → `running` → `succeeded`, or `dead` when it has failed for good, or `canceled`. Succeeded, dead and canceled are final. The one way back is a manual retry of a dead-lettered job.
- **Tenant**: every tenant-facing route takes an `X-Tenant-Id` header. A tenant sees and changes only its own jobs and batches.
- **Batch**: a group of jobs created together. A batch finishes when every job in it has ended (succeeded, dead or canceled): `completed` if none died, otherwise `completed_with_errors`. If the batch has a `callback_url`, finishing it queues one `batch.callback` job on the `callbacks` queue. A batch finishes once; retrying one of its jobs later does not reopen it.

## Worker protocol

Workers call the `/worker/*` routes with the shared `X-Worker-Token`.

1. `POST /worker/claim {queue, worker_id}` hands the worker the highest-priority job that is due, or `204` if there is none. Each job runs on one worker at a time.
2. A claim gives the worker a lease on the job. The worker keeps it by calling `POST /worker/jobs/{id}/heartbeat` at least every 90 seconds during long work. A heartbeat from a worker that no longer holds the job gets `409`.
3. `POST /worker/jobs/{id}/complete {worker_id, output}` marks the job succeeded and stores its output.
4. `POST /worker/jobs/{id}/fail {worker_id, error, retryable}` schedules another attempt after an exponential backoff (10 s, 20 s, 40 s ... capped at one hour), or dead-letters the job when it is out of attempts or `retryable` is false.

Workers may repeat a complete or fail call when the first one timed out; each report takes effect once.

`POST /worker/recover` is the sweeper, run every minute by cron. It takes back every job whose lease has lapsed (90 seconds without a heartbeat): the job goes back on the queue after the usual backoff, or is dead-lettered if it has used all its attempts.

`app/worker.py` has an in-process `Worker` that runs this loop against the database directly, used by the bundled handlers and by the tests.

## Tenant routes

| route | what it does |
|---|---|
| `POST /jobs` | enqueue a job. With an `idempotency_key`, repeating the request returns the original job (`200`) instead of a new one |
| `GET /jobs?status=` | list the tenant's jobs |
| `GET /jobs/{id}`, `GET /jobs/{id}/outputs` | one job and the outputs it produced |
| `POST /jobs/{id}/cancel` | cancel a queued or running job. A running job's worker loses its lease and its later reports are refused |
| `POST /jobs/{id}/retry` | send a dead-lettered job back to the queue with a fresh attempt budget |
| `POST /batches`, `GET /batches/{id}` | create a batch of jobs; read its status and per-status counts |

Errors come back as Problem Details JSON (`404` unknown job, `409` lease lost or wrong state).

## Running

```
./run_tests.sh
```
