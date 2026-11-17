from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.deps import current_user, get_session, require_owner
from app.models import Membership
from app.schemas import MemberIn, MemberOut, WorkspaceIn, WorkspaceOut
from app.services import workspaces

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


@router.post("", status_code=201, response_model=WorkspaceOut)
def create_workspace(body: WorkspaceIn, user_id: str = Depends(current_user), session: Session = Depends(get_session)):
    return workspaces.create_workspace(session, body.name, user_id)


@router.get("", response_model=list[WorkspaceOut])
def my_workspaces(user_id: str = Depends(current_user), session: Session = Depends(get_session)):
    return workspaces.workspaces_for(session, user_id)


@router.post("/{workspace_id}/members", status_code=201, response_model=MemberOut)
def add_member(body: MemberIn, owner: Membership = Depends(require_owner), session: Session = Depends(get_session)):
    return workspaces.add_member(session, owner.workspace, body.user_id, body.role)


@router.delete("/{workspace_id}", status_code=204)
def delete_workspace(owner: Membership = Depends(require_owner), session: Session = Depends(get_session)):
    workspaces.delete_workspace(session, owner.workspace)
    return Response(status_code=204)


@router.post("/{workspace_id}/restore", response_model=WorkspaceOut)
def restore_workspace(owner: Membership = Depends(require_owner), session: Session = Depends(get_session)):
    return workspaces.restore_workspace(session, owner.workspace)
