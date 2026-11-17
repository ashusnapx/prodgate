import hashlib

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.clock import utcnow
from app.config import settings
from app.models import Document, DocumentStatus, Reading
from app.services import projects, readings
from app.services.errors import Conflict, InvalidUpload, NotFound

ACCEPTED_TYPES = {"text/plain", "text/markdown", "text/csv", "application/pdf", "application/json"}


def get_document(db: Session, org_id: str, doc_id: int) -> Document:
    doc = db.get(Document, doc_id)
    if doc is None or doc.org_id != org_id:
        raise NotFound("document", doc_id)
    return doc


def list_documents(db: Session, org_id: str, project_code: str, include_withdrawn: bool = False) -> list[Document]:
    query = select(Document).where(Document.org_id == org_id, Document.project_code == project_code)
    if not include_withdrawn:
        query = query.where(Document.status != DocumentStatus.WITHDRAWN)
    return list(db.scalars(query.order_by(Document.created_at, Document.id)))


def upload_document(
    db: Session,
    org_id: str,
    project_code: str,
    filename: str,
    content_type: str,
    data: bytes,
    uploaded_by: str,
) -> tuple[Document, Reading | None]:
    """Store a new document and start its first reading. A repeat of a live file returns it with no reading."""
    project = projects.get_project(db, org_id, project_code)
    if not data:
        raise InvalidUpload("file is empty")
    if len(data) > settings.max_upload_bytes:
        raise InvalidUpload("file is too large")
    if content_type not in ACCEPTED_TYPES:
        raise InvalidUpload(f"unsupported content type {content_type}")

    digest = hashlib.sha256(data).hexdigest()
    existing = db.scalar(
        select(Document).where(
            Document.org_id == org_id,
            Document.project_code == project.code,
            Document.content_hash == digest,
            Document.status != DocumentStatus.WITHDRAWN,
        )
    )
    if existing is not None:
        return existing, None

    now = utcnow()
    doc = Document(
        org_id=org_id,
        project_code=project.code,
        filename=filename,
        content_type=content_type,
        size=len(data),
        content_hash=digest,
        content=data,
        status=DocumentStatus.PROCESSING,
        uploaded_by=uploaded_by,
        created_at=now,
        updated_at=now,
    )
    db.add(doc)
    db.flush()
    reading = readings.new_reading(db, doc)
    db.commit()
    return doc, reading


def withdraw_document(db: Session, org_id: str, doc_id: int) -> Document:
    doc = get_document(db, org_id, doc_id)
    if doc.status == DocumentStatus.WITHDRAWN:
        raise Conflict(f"document {doc_id} is already withdrawn")

    seen = doc.status
    now = utcnow()
    result = db.execute(
        update(Document)
        .where(Document.id == doc.id, Document.status == seen)
        .values(status=DocumentStatus.WITHDRAWN, status_before_withdraw=seen, withdrawn_at=now, updated_at=now)
    )
    if result.rowcount == 0:
        db.rollback()
        raise Conflict(f"document {doc_id} changed while withdrawing; try again")
    db.commit()
    db.refresh(doc)
    return doc


def restore_document(db: Session, org_id: str, doc_id: int) -> Document:
    doc = get_document(db, org_id, doc_id)
    if doc.status != DocumentStatus.WITHDRAWN:
        raise Conflict(f"document {doc_id} is not withdrawn")

    result = db.execute(
        update(Document)
        .where(Document.id == doc.id, Document.status == DocumentStatus.WITHDRAWN)
        .values(
            status=doc.status_before_withdraw or DocumentStatus.READY,
            status_before_withdraw=None,
            withdrawn_at=None,
            updated_at=utcnow(),
        )
    )
    if result.rowcount == 0:
        db.rollback()
        raise Conflict(f"document {doc_id} is not withdrawn")
    db.commit()
    db.refresh(doc)
    return doc
