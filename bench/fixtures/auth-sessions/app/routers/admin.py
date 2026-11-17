from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session as DbSession

from app.db import get_db
from app.deps import require_admin
from app.models import User
from app.schemas import InviteCreated, InviteOut, InviteRequest, ResetOut, UserOut
from app.services import users

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/users", response_model=list[UserOut])
def list_users(admin: User = Depends(require_admin), db: DbSession = Depends(get_db)):
    return users.list_users(db, admin.org_id)


@router.post("/invites", response_model=InviteCreated, status_code=status.HTTP_201_CREATED)
def invite(body: InviteRequest, admin: User = Depends(require_admin), db: DbSession = Depends(get_db)):
    created, temp = users.create_invite(db, admin, body.email, body.display_name, body.role)
    return InviteCreated(invite=InviteOut.model_validate(created), temporary_password=temp)


@router.post("/invites/{invite_id}/revoke", response_model=InviteOut)
def revoke_invite(invite_id: int, admin: User = Depends(require_admin), db: DbSession = Depends(get_db)):
    return users.revoke_invite(db, admin, invite_id)


@router.post("/users/{user_id}/reset-password", response_model=ResetOut)
def reset_password(user_id: int, admin: User = Depends(require_admin), db: DbSession = Depends(get_db)):
    return ResetOut(temporary_password=users.admin_reset_password(db, admin, user_id))


@router.post("/users/{user_id}/disable", response_model=UserOut)
def disable(user_id: int, admin: User = Depends(require_admin), db: DbSession = Depends(get_db)):
    return users.disable_user(db, admin, user_id)
