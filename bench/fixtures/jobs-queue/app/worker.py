import json
import logging
from collections.abc import Callable
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from app.services import jobs

log = logging.getLogger(__name__)

Handler = Callable[[dict[str, Any], Callable[[], None]], dict[str, Any] | None]


class PermanentError(Exception):
    """Raised by a handler when retrying cannot help (bad payload, missing record)."""


class Worker:
    """Runs jobs from one queue in-process. Handlers get the payload and a beat() to call during long work."""

    def __init__(self, session_factory: sessionmaker[Session], queue: str, worker_id: str, handlers: dict[str, Handler]):
        self.session_factory = session_factory
        self.queue = queue
        self.worker_id = worker_id
        self.handlers = handlers

    def beat(self, job_id: int) -> None:
        with self.session_factory() as db:
            jobs.heartbeat(db, job_id, self.worker_id)

    def run_once(self) -> int | None:
        with self.session_factory() as db:
            job = jobs.claim_next_job(db, self.queue, self.worker_id)
            if job is None:
                return None
            job_id, kind, payload = job.id, job.kind, json.loads(job.payload)

        handler = self.handlers.get(kind)
        try:
            if handler is None:
                raise PermanentError(f"no handler registered for {kind!r}")
            output = handler(payload, lambda: self.beat(job_id))
        except jobs.LeaseLost:
            log.warning("lost job %s while running it", job_id)
            return job_id
        except PermanentError as exc:
            self._fail(job_id, str(exc), retryable=False)
        except Exception as exc:  # anything else is treated as transient
            log.exception("job %s failed", job_id)
            self._fail(job_id, f"{type(exc).__name__}: {exc}", retryable=True)
        else:
            with self.session_factory() as db:
                jobs.complete_job(db, job_id, self.worker_id, output)
        return job_id

    def run_until_empty(self, limit: int = 1000) -> list[int]:
        done: list[int] = []
        while len(done) < limit:
            job_id = self.run_once()
            if job_id is None:
                break
            done.append(job_id)
        return done

    def _fail(self, job_id: int, error: str, retryable: bool) -> None:
        with self.session_factory() as db:
            try:
                jobs.fail_job(db, job_id, self.worker_id, error, retryable=retryable)
            except jobs.LeaseLost:
                log.warning("could not report failure for job %s: lease lost", job_id)
