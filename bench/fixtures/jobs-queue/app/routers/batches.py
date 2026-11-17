from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import current_tenant
from app.models import Batch
from app.schemas import BatchCreate, BatchOut
from app.services import batches

router = APIRouter(prefix="/batches", tags=["batches"])


def _out(db: Session, batch: Batch) -> BatchOut:
    counts = {s.value: n for s, n in batches.job_counts(db, batch.id).items()}
    return BatchOut(
        id=batch.id,
        name=batch.name,
        status=batch.status,
        total_jobs=batch.total_jobs,
        counts=counts,
        created_at=batch.created_at,
        finished_at=batch.finished_at,
    )


@router.post("", response_model=BatchOut, status_code=status.HTTP_201_CREATED)
def create_batch(body: BatchCreate, tenant: str = Depends(current_tenant), db: Session = Depends(get_db)):
    specs = [spec.model_dump() for spec in body.jobs]
    batch = batches.create_batch(db, tenant, body.name, specs, callback_url=body.callback_url)
    return _out(db, batch)


@router.get("/{batch_id}", response_model=BatchOut)
def get_batch(batch_id: int, tenant: str = Depends(current_tenant), db: Session = Depends(get_db)):
    return _out(db, batches.get_batch_for_tenant(db, tenant, batch_id))
