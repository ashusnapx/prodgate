import json
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.clock import utcnow
from app.config import settings
from app.models import TERMINAL_STATUSES, Job, JobEvent, JobOutput, JobStatus
from app.services import batches


class JobNotFound(Exception):
    pass


class LeaseLost(Exception):
    """The caller no longer holds the job (it was recovered, canceled or finished)."""


class InvalidJobState(Exception):
    pass


def record_event(db: Session, job: Job, event: str, *, worker: str | None = None, detail: str | None = None) -> None:
    db.add(JobEvent(job_id=job.id, event=event, worker=worker, detail=detail))


def retry_delay(attempts: int) -> timedelta:
    seconds = settings.retry_base_seconds * 2 ** max(attempts - 1, 0)
    return timedelta(seconds=min(seconds, settings.retry_max_seconds))


def get_job(db: Session, job_id: int) -> Job:
    job = db.get(Job, job_id)
    if job is None:
        raise JobNotFound(job_id)
    return job


def get_job_for_tenant(db: Session, tenant_id: str, job_id: int) -> Job:
    job = db.get(Job, job_id)
    if job is None or job.tenant_id != tenant_id:
        raise JobNotFound(job_id)
    return job


def list_jobs(db: Session, tenant_id: str, status: JobStatus | None = None, limit: int = 100) -> list[Job]:
    query = select(Job).where(Job.tenant_id == tenant_id)
    if status is not None:
        query = query.where(Job.status == status)
    return list(db.scalars(query.order_by(Job.id.desc()).limit(limit)))


def build_job(tenant_id: str, spec: dict[str, Any], batch_id: int | None = None) -> Job:
    return Job(
        tenant_id=tenant_id,
        queue=spec["queue"],
        kind=spec["kind"],
        payload=json.dumps(spec.get("payload") or {}),
        priority=spec.get("priority") or 0,
        max_attempts=spec.get("max_attempts") or settings.default_max_attempts,
        run_after=spec.get("run_after") or utcnow(),
        idempotency_key=spec.get("idempotency_key"),
        batch_id=batch_id,
    )


def enqueue_job(db: Session, tenant_id: str, spec: dict[str, Any]) -> tuple[Job, bool]:
    """Add a job. Returns (job, created); a repeated idempotency key returns the original job."""
    key = spec.get("idempotency_key")
    if key:
        existing = db.scalar(select(Job).where(Job.tenant_id == tenant_id, Job.idempotency_key == key))
        if existing is not None:
            return existing, False

    job = build_job(tenant_id, spec)
    db.add(job)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        existing = db.scalar(select(Job).where(Job.tenant_id == tenant_id, Job.idempotency_key == key))
        return existing, False
    record_event(db, job, "enqueued")
    db.commit()
    return job, True


def claim_next_job(db: Session, queue: str, worker_id: str) -> Job | None:
    now = utcnow()
    job = db.scalars(
        select(Job)
        .where(Job.queue == queue, Job.status == JobStatus.QUEUED, Job.run_after <= now)
        .order_by(Job.priority.desc(), Job.id)
        .limit(1)
    ).first()
    if job is None:
        return None

    job.status = JobStatus.RUNNING
    job.lease_owner = worker_id
    job.attempts += 1
    job.started_at = now
    job.last_error = None
    record_event(db, job, "claimed", worker=worker_id)
    db.commit()
    return job


def heartbeat(db: Session, job_id: int, worker_id: str) -> None:
    result = db.execute(
        update(Job)
        .where(Job.id == job_id, Job.status == JobStatus.RUNNING, Job.lease_owner == worker_id)
        .values(last_heartbeat_at=utcnow())
    )
    db.commit()
    if result.rowcount == 0:
        raise LeaseLost(job_id)


def complete_job(db: Session, job_id: int, worker_id: str, output: dict[str, Any] | None = None) -> Job:
    job = get_job(db, job_id)
    now = utcnow()
    result = db.execute(
        update(Job)
        .where(Job.id == job_id, Job.lease_owner == worker_id)
        .values(status=JobStatus.SUCCEEDED, finished_at=now)
    )
    if result.rowcount == 0:
        db.rollback()
        raise LeaseLost(job_id)
    if output is not None:
        db.add(JobOutput(job_id=job_id, data=json.dumps(output)))
    record_event(db, job, "succeeded", worker=worker_id)
    db.commit()
    db.refresh(job)
    if job.batch_id is not None:
        batches.on_job_finished(db, job.batch_id)
    return job


def fail_job(db: Session, job_id: int, worker_id: str, error: str, retryable: bool = True) -> Job:
    job = get_job(db, job_id)
    if job.status != JobStatus.RUNNING or job.lease_owner != worker_id:
        raise LeaseLost(job_id)

    now = utcnow()
    will_retry = retryable and job.attempts < job.max_attempts
    values: dict[str, Any] = {"lease_owner": None, "last_error": error[:2000]}
    if will_retry:
        values.update(status=JobStatus.QUEUED, run_after=now + retry_delay(job.attempts))
    else:
        values.update(status=JobStatus.DEAD, finished_at=now)

    result = db.execute(
        update(Job)
        .where(Job.id == job_id, Job.status == JobStatus.RUNNING, Job.lease_owner == worker_id)
        .values(**values)
    )
    if result.rowcount == 0:
        db.rollback()
        raise LeaseLost(job_id)
    record_event(db, job, "retry_scheduled" if will_retry else "dead_lettered", worker=worker_id, detail=error)
    db.commit()
    db.refresh(job)
    if not will_retry and job.batch_id is not None:
        batches.on_job_finished(db, job.batch_id)
    return job


def mark_dead(db: Session, job: Job, reason: str, now: datetime) -> None:
    job.status = JobStatus.DEAD
    job.lease_owner = None
    job.last_error = reason
    job.finished_at = now
    record_event(db, job, "dead_lettered", detail=reason)


def cancel_job(db: Session, job_id: int, reason: str | None = None) -> Job:
    job = get_job(db, job_id)
    if job.status in TERMINAL_STATUSES:
        raise InvalidJobState(f"job {job_id} is already {job.status.value}")

    job.status = JobStatus.CANCELED
    job.lease_owner = None
    job.finished_at = utcnow()
    record_event(db, job, "canceled", detail=reason)
    db.commit()
    if job.batch_id is not None:
        batches.on_job_finished(db, job.batch_id)
    return job


def retry_job(db: Session, tenant_id: str, job_id: int) -> Job:
    """Send a finished job back to the queue with a fresh attempt budget."""
    job = get_job_for_tenant(db, tenant_id, job_id)
    if job.status in (JobStatus.QUEUED, JobStatus.RUNNING):
        raise InvalidJobState(f"job {job_id} is still {job.status.value}")

    job.status = JobStatus.QUEUED
    job.attempts = 0
    job.run_after = utcnow()
    job.finished_at = None
    job.last_error = None
    record_event(db, job, "manually_retried")
    db.commit()
    return job
