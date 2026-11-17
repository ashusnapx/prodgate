from fastapi import APIRouter, BackgroundTasks, Depends, Request, Response
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import current_org
from app.models import DocumentStatus
from app.schemas import DocumentOut, ReadingOut, ReadingSummary
from app.services import documents, readings
from app.services.errors import Conflict, NotFound

router = APIRouter(tags=["documents"])


@router.get("/documents/{doc_id}", response_model=DocumentOut)
def get_document(doc_id: int, org: str = Depends(current_org), db: Session = Depends(get_db)):
    return documents.get_document(db, org, doc_id)


@router.get("/documents/{doc_id}/content")
def download(doc_id: int, org: str = Depends(current_org), db: Session = Depends(get_db)):
    doc = documents.get_document(db, org, doc_id)
    if doc.status == DocumentStatus.WITHDRAWN:
        raise NotFound("document", doc_id)
    headers = {"Content-Disposition": f'attachment; filename="{doc.filename}"'}
    return Response(content=doc.content, media_type=doc.content_type, headers=headers)


@router.post("/documents/{doc_id}/withdraw", response_model=DocumentOut)
def withdraw(doc_id: int, org: str = Depends(current_org), db: Session = Depends(get_db)):
    return documents.withdraw_document(db, org, doc_id)


@router.post("/documents/{doc_id}/restore", response_model=DocumentOut)
def restore(doc_id: int, org: str = Depends(current_org), db: Session = Depends(get_db)):
    return documents.restore_document(db, org, doc_id)


@router.post("/documents/{doc_id}/reread", response_model=ReadingSummary, status_code=202)
def reread(doc_id: int, request: Request, background: BackgroundTasks, org: str = Depends(current_org), db: Session = Depends(get_db)):
    doc = documents.get_document(db, org, doc_id)
    if doc.status == DocumentStatus.WITHDRAWN:
        raise Conflict(f"document {doc_id} is withdrawn")
    reading = readings.start_reread(db, doc)
    background.add_task(request.app.state.reader.submit, reading.id, doc.content_type, doc.content)
    return reading


@router.get("/documents/{doc_id}/readings", response_model=list[ReadingSummary])
def list_readings(doc_id: int, org: str = Depends(current_org), db: Session = Depends(get_db)):
    return documents.get_document(db, org, doc_id).readings


@router.get("/documents/{doc_id}/reading", response_model=ReadingOut)
def current_reading(doc_id: int, org: str = Depends(current_org), db: Session = Depends(get_db)):
    doc = documents.get_document(db, org, doc_id)
    reading = readings.current_reading(db, doc.id) if doc.status != DocumentStatus.WITHDRAWN else None
    if reading is None:
        raise NotFound("current reading for document", doc_id)
    return reading


@router.get("/readings/{reading_id}", response_model=ReadingOut)
def get_reading(reading_id: int, db: Session = Depends(get_db)):
    return readings.get_reading(db, reading_id)
