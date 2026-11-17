from datetime import timedelta

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.clock import utcnow
from app.config import settings
from app.models import Document, DocumentStatus, Reading, ReadingState
from app.services.errors import Conflict, NotFound


def new_reading(db: Session, doc: Document) -> Reading:
    latest = db.scalar(select(func.max(Reading.version)).where(Reading.document_id == doc.id)) or 0
    reading = Reading(org_id=doc.org_id, document_id=doc.id, version=latest + 1, started_at=utcnow())
    db.add(reading)
    db.flush()
    return reading


def get_reading(db: Session, reading_id: int) -> Reading:
    reading = db.get(Reading, reading_id)
    if reading is None:
        raise NotFound("reading", reading_id)
    return reading


def current_reading(db: Session, doc_id: int) -> Reading | None:
    return db.scalar(select(Reading).where(Reading.document_id == doc_id, Reading.is_current.is_(True)))


def start_reread(db: Session, doc: Document) -> Reading:
    """Read the document again; the new reading replaces the current one when it finishes."""
    result = db.execute(
        update(Document)
        .where(Document.id == doc.id, Document.status.in_([DocumentStatus.READY, DocumentStatus.FAILED]))
        .values(status=DocumentStatus.PROCESSING, updated_at=utcnow())
    )
    if result.rowcount == 0:
        db.rollback()
        raise Conflict(f"document {doc.id} cannot be re-read while {doc.status.value}")
    reading = new_reading(db, doc)
    db.commit()
    db.refresh(doc)
    return reading


def complete_reading(db: Session, reading_id: int, text: str, page_count: int | None) -> Reading:
    reading = get_reading(db, reading_id)
    if reading.state != ReadingState.RUNNING:
        return reading

    now = utcnow()
    db.execute(
        update(Reading)
        .where(Reading.document_id == reading.document_id, Reading.is_current.is_(True))
        .values(is_current=False, state=ReadingState.SUPERSEDED)
    )
    reading.state = ReadingState.DONE
    reading.is_current = True
    reading.text = text
    reading.page_count = page_count
    reading.finished_at = now

    doc = reading.document
    doc.status = DocumentStatus.READY
    doc.updated_at = now
    db.commit()
    return reading


def fail_reading(db: Session, reading_id: int, error: str) -> Reading:
    reading = get_reading(db, reading_id)
    now = utcnow()
    reading.state = ReadingState.FAILED
    reading.is_current = False
    reading.error = error[:2000]
    reading.finished_at = now

    doc = reading.document
    if doc.status == DocumentStatus.PROCESSING:
        has_current = db.scalar(
            select(func.count()).where(
                Reading.document_id == doc.id, Reading.is_current.is_(True), Reading.id != reading.id
            )
        )
        doc.status = DocumentStatus.READY if has_current else DocumentStatus.FAILED
        doc.updated_at = now
    db.commit()
    return reading


def expire_stale_readings(db: Session) -> int:
    """Fail readings the reader never answered."""
    now = utcnow()
    cutoff = now - timedelta(minutes=settings.reading_timeout_minutes)
    result = db.execute(
        update(Reading)
        .where(Reading.state == ReadingState.RUNNING, Reading.started_at < cutoff)
        .values(state=ReadingState.FAILED, error="reader did not answer in time", finished_at=now)
    )
    db.commit()
    return result.rowcount


def search(db: Session, org_id: str, project_code: str, term: str, limit: int = 20) -> list[tuple[Document, Reading]]:
    escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    pattern = f"%{escaped}%"
    rows = db.execute(
        select(Document, Reading)
        .join(Reading, Reading.document_id == Document.id)
        .where(
            Document.org_id == org_id,
            Document.project_code == project_code,
            Document.status == DocumentStatus.READY,
            Reading.is_current.is_(True),
            Reading.text.ilike(pattern, escape="\\"),
        )
        .order_by(Document.id)
        .limit(limit)
    )
    return [(doc, reading) for doc, reading in rows]
