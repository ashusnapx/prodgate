from collections.abc import Iterator

from fastapi import Depends, Header, Request
from sqlalchemy.orm import Session

from app.errors import Forbidden, NotFound
from app.models import Membership


def get_session(request: Request) -> Iterator[Session]:
    session = request.app.state.sessionmaker()
    try:
        yield session
    finally:
        session.close()


def current_user(x_user_id: str = Header(min_length=1, max_length=64)) -> str:
    return x_user_id


def require_member(
    workspace_id: int, user_id: str = Depends(current_user), session: Session = Depends(get_session)
) -> Membership:
    membership = session.get(Membership, (workspace_id, user_id))
    if membership is None:
        raise NotFound(f"workspace {workspace_id}")
    return membership


def require_live_member(membership: Membership = Depends(require_member)) -> Membership:
    if membership.workspace.deleted_at is not None:
        raise NotFound(f"workspace {membership.workspace_id}")
    return membership


def can_edit(membership: Membership) -> bool:
    return membership.role in ("owner", "editor")


def require_editor(membership: Membership = Depends(require_live_member)) -> Membership:
    if not can_edit(membership):
        raise Forbidden("editors only")
    return membership


def require_owner(membership: Membership = Depends(require_member)) -> Membership:
    if membership.role != "owner":
        raise Forbidden("owners only")
    return membership
