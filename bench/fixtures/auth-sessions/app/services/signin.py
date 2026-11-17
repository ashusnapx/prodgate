from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

from app.clock import utcnow
from app.config import settings
from app.models import Invite, InviteStatus, SignInBucket, User, UserStatus
from app.security import normalize_email, verify_password
from app.services import sessions, users
from app.services.errors import InvalidCredentials, InviteExpired, RateLimited


def check_rate_limit(db: DbSession, key: str, now: datetime) -> None:
    """Count one attempt against `key`; raise once the window's allowance is used up."""
    bucket = db.get(SignInBucket, key)
    if bucket is None:
        db.add(SignInBucket(key=key, window_started_at=now, attempts=0))
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
    elif now - bucket.window_started_at >= settings.sign_in_window:
        db.execute(
            update(SignInBucket)
            .where(SignInBucket.key == key, SignInBucket.window_started_at == bucket.window_started_at)
            .values(window_started_at=now, attempts=0)
        )
        db.commit()

    result = db.execute(
        update(SignInBucket)
        .where(SignInBucket.key == key, SignInBucket.attempts < settings.sign_in_max_attempts)
        .values(attempts=SignInBucket.attempts + 1)
    )
    db.commit()
    if result.rowcount == 0:
        raise RateLimited()


def sign_in(db: DbSession, email: str, password: str, user_agent: str | None = None) -> tuple[str, User]:
    email = normalize_email(email)
    now = utcnow()
    check_rate_limit(db, f"sign-in:{email}", now)

    user = users.get_user_by_email(db, email)
    if user is None or user.status == UserStatus.DISABLED or not verify_password(password, user.password_hash):
        raise InvalidCredentials()
    if user.status == UserStatus.INVITED:
        _accept_invite(db, user, now)

    token = sessions.open_session(db, user, user_agent)
    users.audit(db, user.org_id, user.id, "signed_in", user.id)
    db.commit()
    return token, user


def _accept_invite(db: DbSession, user: User, now: datetime) -> None:
    invite = db.scalar(
        select(Invite).where(Invite.user_id == user.id).order_by(Invite.created_at.desc(), Invite.id.desc()).limit(1)
    )
    if invite is None or invite.expires_at <= now:
        raise InviteExpired()

    db.execute(update(Invite).where(Invite.id == invite.id).values(status=InviteStatus.ACCEPTED, accepted_at=now))
    result = db.execute(
        update(User).where(User.id == user.id, User.status == UserStatus.INVITED).values(status=UserStatus.ACTIVE)
    )
    if result.rowcount == 0:
        db.rollback()
        raise InvalidCredentials()
    users.audit(db, user.org_id, user.id, "invite_accepted", user.id)
    db.commit()
    db.refresh(user)
