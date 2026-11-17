from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.clock import utcnow
from app.config import settings
from app.models import Job, JobStatus
from app.services import batches
from app.services.jobs import mark_dead, record_event, retry_delay


def find_stale_jobs(db: Session, now: datetime) -> list[Job]:
    cutoff = now - timedelta(seconds=settings.heartbeat_timeout_seconds)
    return list(
        db.scalars(
            select(Job)
            .where(Job.status == JobStatus.RUNNING, Job.last_heartbeat_at < cutoff)
            .order_by(Job.id)
        )
    )


def recover_stale_jobs(db: Session) -> list[int]:
    """Put jobs whose worker went quiet back on the queue, or dead-letter them if out of attempts."""
    now = utcnow()
    recovered: list[int] = []
    touched_batches: set[int] = set()

    for job in find_stale_jobs(db, now):
        job.lease_owner = None
        if job.attempts >= job.max_attempts:
            mark_dead(db, job, "worker stopped sending heartbeats", now)
            if job.batch_id is not None:
                touched_batches.add(job.batch_id)
        else:
            job.status = JobStatus.QUEUED
            job.run_after = now + retry_delay(job.attempts)
            record_event(db, job, "recovered", detail="worker stopped sending heartbeats")
        recovered.append(job.id)

    db.commit()
    for batch_id in touched_batches:
        batches.on_job_finished(db, batch_id)
    return recovered
