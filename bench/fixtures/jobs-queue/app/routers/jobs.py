from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import current_tenant
from app.models import JobStatus
from app.schemas import CancelRequest, JobCreate, JobOut, JobOutputOut
from app.services import jobs

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.post("", response_model=JobOut, status_code=status.HTTP_201_CREATED)
def create_job(body: JobCreate, response: Response, tenant: str = Depends(current_tenant), db: Session = Depends(get_db)):
    job, created = jobs.enqueue_job(db, tenant, body.model_dump())
    if not created:
        response.status_code = status.HTTP_200_OK
    return job


@router.get("", response_model=list[JobOut])
def list_jobs(status: JobStatus | None = None, limit: int = 100, tenant: str = Depends(current_tenant), db: Session = Depends(get_db)):
    return jobs.list_jobs(db, tenant, status=status, limit=min(limit, 500))


@router.get("/{job_id}", response_model=JobOut)
def get_job(job_id: int, tenant: str = Depends(current_tenant), db: Session = Depends(get_db)):
    return jobs.get_job_for_tenant(db, tenant, job_id)


@router.get("/{job_id}/outputs", response_model=list[JobOutputOut])
def get_outputs(job_id: int, tenant: str = Depends(current_tenant), db: Session = Depends(get_db)):
    return jobs.get_job_for_tenant(db, tenant, job_id).outputs


@router.post("/{job_id}/cancel", response_model=JobOut)
def cancel_job(job_id: int, body: CancelRequest | None = None, db: Session = Depends(get_db)):
    return jobs.cancel_job(db, job_id, reason=body.reason if body else None)


@router.post("/{job_id}/retry", response_model=JobOut)
def retry_job(job_id: int, tenant: str = Depends(current_tenant), db: Session = Depends(get_db)):
    return jobs.retry_job(db, tenant, job_id)
