from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import require_worker
from app.schemas import ClaimRequest, CompleteRequest, FailRequest, JobOut, WorkerRequest
from app.services import jobs, recovery

router = APIRouter(prefix="/worker", tags=["worker"], dependencies=[Depends(require_worker)])


@router.post("/claim", response_model=JobOut | None)
def claim(body: ClaimRequest, db: Session = Depends(get_db)):
    job = jobs.claim_next_job(db, body.queue, body.worker_id)
    if job is None:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    return job


@router.post("/jobs/{job_id}/heartbeat", status_code=status.HTTP_204_NO_CONTENT)
def heartbeat(job_id: int, body: WorkerRequest, db: Session = Depends(get_db)):
    jobs.heartbeat(db, job_id, body.worker_id)


@router.post("/jobs/{job_id}/complete", response_model=JobOut)
def complete(job_id: int, body: CompleteRequest, db: Session = Depends(get_db)):
    return jobs.complete_job(db, job_id, body.worker_id, body.output)


@router.post("/jobs/{job_id}/fail", response_model=JobOut)
def fail(job_id: int, body: FailRequest, db: Session = Depends(get_db)):
    return jobs.fail_job(db, job_id, body.worker_id, body.error, retryable=body.retryable)


@router.post("/recover")
def recover(db: Session = Depends(get_db)):
    return {"recovered": recovery.recover_stale_jobs(db)}
