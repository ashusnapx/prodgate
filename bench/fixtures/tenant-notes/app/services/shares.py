import secrets
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import NotFound
from app.models import Note, ShareLink, utcnow


def create_share(session: Session, note: Note, user_id: str, expires_in: timedelta | None) -> ShareLink:
    link = ShareLink(
        note_id=note.id,
        token=secrets.token_urlsafe(24),
        created_by=user_id,
        expires_at=utcnow() + expires_in if expires_in else None,
    )
    session.add(link)
    session.commit()
    return link


def shares_for_note(session: Session, note_id: int) -> list[ShareLink]:
    return list(session.scalars(select(ShareLink).where(ShareLink.note_id == note_id).order_by(ShareLink.id)))


def revoke_share(session: Session, link: ShareLink) -> ShareLink:
    if link.revoked_at is None:
        link.revoked_at = utcnow()
        session.commit()
    return link


def find_by_token(session: Session, token: str) -> ShareLink | None:
    return session.scalar(select(ShareLink).where(ShareLink.token == token))


def is_expired(link: ShareLink, now: datetime) -> bool:
    return link.expires_at is not None and link.expires_at <= now


def resolve_share(session: Session, token: str, now: datetime | None = None) -> ShareLink:
    link = find_by_token(session, token)
    if link is None or link.revoked_at is not None or is_expired(link, now or utcnow()):
        raise NotFound("share link")
    if link.note.deleted_at is not None:
        raise NotFound("share link")
    return link


def render_note_markdown(note: Note) -> str:
    return f"# {note.title}\n\n{note.body.rstrip()}\n"
