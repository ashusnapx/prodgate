from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.errors import Conflict
from app.models import Membership, Note, Workspace, utcnow

ROLES = ("owner", "editor", "viewer")


def create_workspace(session: Session, name: str, owner_id: str) -> Workspace:
    workspace = Workspace(name=name)
    session.add(workspace)
    session.flush()
    session.add(Membership(workspace_id=workspace.id, user_id=owner_id, role="owner"))
    session.commit()
    return workspace


def workspaces_for(session: Session, user_id: str) -> list[Workspace]:
    query = (
        select(Workspace)
        .join(Membership, Membership.workspace_id == Workspace.id)
        .where(Membership.user_id == user_id, Workspace.deleted_at.is_(None))
        .order_by(Workspace.name)
    )
    return list(session.scalars(query))


def add_member(session: Session, workspace: Workspace, user_id: str, role: str) -> Membership:
    if workspace.deleted_at is not None:
        raise Conflict(f"workspace {workspace.id} is deleted")
    membership = session.get(Membership, (workspace.id, user_id))
    if membership is None:
        membership = Membership(workspace_id=workspace.id, user_id=user_id, role=role)
        session.add(membership)
    else:
        membership.role = role
    session.commit()
    return membership


def delete_workspace(session: Session, workspace: Workspace) -> None:
    if workspace.deleted_at is not None:
        raise Conflict(f"workspace {workspace.id} is already deleted")
    deleted_at = utcnow()
    workspace.deleted_at = deleted_at
    session.execute(
        update(Note)
        .where(Note.workspace_id == workspace.id, Note.deleted_at.is_(None))
        .values(deleted_at=deleted_at)
    )
    session.commit()


def restore_workspace(session: Session, workspace: Workspace) -> Workspace:
    if workspace.deleted_at is None:
        raise Conflict(f"workspace {workspace.id} is not deleted")
    session.execute(
        update(Note)
        .where(Note.workspace_id == workspace.id, Note.deleted_at == workspace.deleted_at)
        .values(deleted_at=None)
    )
    workspace.deleted_at = None
    session.commit()
    return workspace
