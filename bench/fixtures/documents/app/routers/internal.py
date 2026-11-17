from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import require_reader
from app.schemas import ReaderError, ReaderResult, ReadingSummary
from app.services import readings

router = APIRouter(prefix="/internal", tags=["internal"], dependencies=[Depends(require_reader)])


@router.post("/readings/{reading_id}/result", response_model=ReadingSummary)
def reading_result(reading_id: int, body: ReaderResult, db: Session = Depends(get_db)):
    return readings.complete_reading(db, reading_id, body.text, body.page_count)


@router.post("/readings/{reading_id}/error", response_model=ReadingSummary)
def reading_error(reading_id: int, body: ReaderError, db: Session = Depends(get_db)):
    return readings.fail_reading(db, reading_id, body.error)


@router.post("/readings/expire")
def expire(db: Session = Depends(get_db)):
    return {"expired": readings.expire_stale_readings(db)}
