from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session as DbSession

from app.db import get_db
from app.models import Role, Session, User
from app.services import sessions
from app.services.errors import NotAuthenticated


@dataclass
class Auth:
    session: Session
    user: User


def current_auth(authorization: str | None = Header(default=None), db: DbSession = Depends(get_db)) -> Auth:
    if not authorization or not authorization.startswith("Bearer "):
        raise NotAuthenticated()
    session, user = sessions.authenticate(db, authorization.removeprefix("Bearer ").strip())
    return Auth(session=session, user=user)


def ready_auth(auth: Auth = Depends(current_auth)) -> Auth:
    """Signed in and not holding a one-time password."""
    if auth.user.must_set_password:
        raise HTTPException(status_code=403, detail="choose a new password first")
    return auth


def require_admin(auth: Auth = Depends(current_auth)) -> User:
    if auth.user.role != Role.ADMIN:
        raise HTTPException(status_code=403, detail="admins only")
    return auth.user
