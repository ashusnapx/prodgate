from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session as DbSession

from app.clock import utcnow
from app.config import settings
from app.models import Session, User, UserStatus
from app.security import new_token, token_digest
from app.services.errors import NotAuthenticated


def open_session(db: DbSession, user: User, user_agent: str | None = None) -> str:
    """Create a session and return its token. Only the token's SHA-256 is stored."""
    token = new_token()
    now = utcnow()
    db.add(
        Session(
            user_id=user.id,
            token_hash=token_digest(token),
            user_agent=(user_agent or "")[:300] or None,
            created_at=now,
            last_seen_at=now,
            expires_at=now + settings.session_idle,
        )
    )
    db.commit()
    return token


def authenticate(db: DbSession, token: str) -> tuple[Session, User]:
    row = db.scalar(select(Session).where(Session.token_hash == token_digest(token)))
    now = utcnow()
    if row is None or row.revoked_at is not None or row.expires_at <= now:
        raise NotAuthenticated()
    user = db.get(User, row.user_id)
    if user is None or user.status != UserStatus.ACTIVE:
        raise NotAuthenticated()
    touch_session(db, row, now)
    return row, user


def touch_session(db: DbSession, row: Session, now: datetime) -> None:
    """Slide the idle expiry forward, at most once per renew interval."""
    if now - row.last_seen_at < settings.session_renew_after:
        return
    db.execute(
        update(Session)
        .where(Session.id == row.id, Session.revoked_at.is_(None))
        .values(last_seen_at=now, expires_at=now + settings.session_idle)
    )
    db.commit()


def list_sessions(db: DbSession, user_id: int) -> list[Session]:
    now = utcnow()
    return list(
        db.scalars(
            select(Session)
            .where(Session.user_id == user_id, Session.revoked_at.is_(None), Session.expires_at > now)
            .order_by(Session.created_at.desc(), Session.id.desc())
        )
    )


def revoke_session(db: DbSession, session_id: int) -> None:
    db.execute(update(Session).where(Session.id == session_id, Session.revoked_at.is_(None)).values(revoked_at=utcnow()))
    db.commit()


def revoke_all_for_user(db: DbSession, user_id: int, except_session_id: int | None = None) -> None:
    query = update(Session).where(Session.user_id == user_id, Session.revoked_at.is_(None))
    if except_session_id is not None:
        query = query.where(Session.id != except_session_id)
    db.execute(query.values(revoked_at=utcnow()))
