from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.clock import utcnow
from app.config import settings
from app.models import Batch, BatchStatus, Job, JobStatus


class BatchNotFound(Exception):
    pass


def get_batch_for_tenant(db: Session, tenant_id: str, batch_id: int) -> Batch:
    batch = db.get(Batch, batch_id)
    if batch is None or batch.tenant_id != tenant_id:
        raise BatchNotFound(batch_id)
    return batch


def create_batch(db: Session, tenant_id: str, name: str, specs: list[dict[str, Any]], callback_url: str | None = None) -> Batch:
    from app.services.jobs import build_job

    batch = Batch(tenant_id=tenant_id, name=name, total_jobs=len(specs), callback_url=callback_url)
    db.add(batch)
    db.flush()
    for spec in specs:
        db.add(build_job(tenant_id, {**spec, "idempotency_key": None}, batch_id=batch.id))
    db.commit()
    return batch


def job_counts(db: Session, batch_id: int) -> dict[JobStatus, int]:
    rows = db.execute(
        select(Job.status, func.count()).where(Job.batch_id == batch_id).group_by(Job.status)
    ).all()
    return {status: count for status, count in rows}


def on_job_finished(db: Session, batch_id: int) -> None:
    """Close the batch once every job in it has ended, and queue its callback."""
    batch = db.get(Batch, batch_id)
    if batch is None or batch.status != BatchStatus.OPEN:
        return

    counts = job_counts(db, batch_id)
    succeeded = counts.get(JobStatus.SUCCEEDED, 0)
    dead = counts.get(JobStatus.DEAD, 0)
    if succeeded + dead < batch.total_jobs:
        return

    final = BatchStatus.COMPLETED if dead == 0 else BatchStatus.COMPLETED_WITH_ERRORS
    result = db.execute(
        update(Batch)
        .where(Batch.id == batch_id, Batch.status == BatchStatus.OPEN)
        .values(status=final, finished_at=utcnow())
    )
    if result.rowcount == 1 and batch.callback_url:
        _queue_callback(db, batch, final, succeeded, dead)
    db.commit()
    db.refresh(batch)


def _queue_callback(db: Session, batch: Batch, final: BatchStatus, succeeded: int, dead: int) -> None:
    from app.services.jobs import build_job

    payload = {
        "batch_id": batch.id,
        "status": final.value,
        "succeeded": succeeded,
        "dead": dead,
        "url": batch.callback_url,
    }
    db.add(build_job(batch.tenant_id, {"queue": settings.callback_queue, "kind": "batch.callback", "payload": payload}))
