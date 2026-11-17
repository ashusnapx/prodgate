from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session as DbSession

from app.db import get_db
from app.deps import Auth, current_auth, ready_auth
from app.schemas import SessionOut, SetPasswordRequest, UserOut
from app.services import sessions, users

router = APIRouter(prefix="/me", tags=["me"])


@router.get("", response_model=UserOut)
def me(auth: Auth = Depends(current_auth)):
    return auth.user


@router.post("/password", status_code=status.HTTP_204_NO_CONTENT)
def set_password(body: SetPasswordRequest, auth: Auth = Depends(current_auth), db: DbSession = Depends(get_db)):
    users.set_own_password(db, auth.user, auth.session.id, body.current_password, body.new_password)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/sessions", response_model=list[SessionOut])
def my_sessions(auth: Auth = Depends(ready_auth), db: DbSession = Depends(get_db)):
    return sessions.list_sessions(db, auth.user.id)


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_session(session_id: int, auth: Auth = Depends(ready_auth), db: DbSession = Depends(get_db)):
    sessions.revoke_session(db, session_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
