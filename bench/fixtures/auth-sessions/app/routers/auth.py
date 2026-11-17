from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.orm import Session as DbSession

from app.db import get_db
from app.deps import Auth, current_auth
from app.schemas import SignInRequest, SignInResponse
from app.services import sessions, signin

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/sign-in", response_model=SignInResponse)
def sign_in(body: SignInRequest, request: Request, db: DbSession = Depends(get_db)):
    token, user = signin.sign_in(db, body.email, body.password, request.headers.get("user-agent"))
    return SignInResponse(token=token, must_set_password=user.must_set_password)


@router.post("/sign-out", status_code=status.HTTP_204_NO_CONTENT)
def sign_out(auth: Auth = Depends(current_auth), db: DbSession = Depends(get_db)):
    sessions.revoke_session(db, auth.session.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
