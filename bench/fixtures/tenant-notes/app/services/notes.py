from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import Conflict, NotFound
from app.models import Note, utcnow


def note_in_workspace(session: Session, workspace_id: int, note_id: int, include_deleted: bool = False) -> Note:
    query = select(Note).where(Note.id == note_id, Note.workspace_id == workspace_id)
    if not include_deleted:
        query = query.where(Note.deleted_at.is_(None))
    note = session.scalar(query)
    if note is None:
        raise NotFound(f"note {note_id}")
    return note


def list_notes(
    session: Session, workspace_id: int, search: str | None = None, limit: int = 50, before_id: int | None = None
) -> list[Note]:
    query = select(Note).where(Note.workspace_id == workspace_id, Note.deleted_at.is_(None))
    if search:
        pattern = f"%{search}%"
        query = query.where(Note.title.ilike(pattern) | Note.body.ilike(pattern))
    if before_id is not None:
        query = query.where(Note.id < before_id)
    return list(session.scalars(query.order_by(Note.id.desc()).limit(limit)))


def list_trash(session: Session, workspace_id: int) -> list[Note]:
    query = select(Note).where(Note.workspace_id == workspace_id, Note.deleted_at.is_not(None))
    return list(session.scalars(query.order_by(Note.deleted_at.desc())))


def _find_by_request(session: Session, workspace_id: int, user_id: str, request_id: str) -> Note | None:
    return session.scalar(
        select(Note).where(
            Note.workspace_id == workspace_id, Note.created_by == user_id, Note.request_id == request_id
        )
    )


def create_note(
    session: Session, workspace_id: int, user_id: str, title: str, body: str, request_id: str | None = None
) -> tuple[Note, bool]:
    if request_id:
        existing = _find_by_request(session, workspace_id, user_id, request_id)
        if existing is not None:
            return existing, False
    note = Note(
        workspace_id=workspace_id,
        title=title,
        body=body,
        created_by=user_id,
        updated_by=user_id,
        request_id=request_id,
    )
    session.add(note)
    session.commit()
    return note, True


def update_note(
    session: Session,
    note: Note,
    user_id: str,
    base_version: int,
    title: str | None = None,
    body: str | None = None,
) -> Note:
    if note.version != base_version:
        raise Conflict(f"note {note.id} is at version {note.version}; your edit was based on {base_version}")
    if title is not None:
        note.title = title
    if body is not None:
        note.body = body
    note.version = note.version + 1
    note.updated_by = user_id
    session.commit()
    return note


def delete_note(session: Session, note: Note) -> None:
    note.deleted_at = utcnow()
    session.commit()


def restore_note(session: Session, note: Note, user_id: str) -> Note:
    if note.deleted_at is None:
        raise Conflict(f"note {note.id} is not in the trash")
    note.deleted_at = None
    note.updated_by = user_id
    session.commit()
    return note
