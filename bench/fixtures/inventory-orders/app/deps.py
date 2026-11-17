import hmac
from collections.abc import Iterator

from fastapi import Header, HTTPException, Request
from sqlalchemy.orm import Session

from app.services.payments import FakeGateway


def get_session(request: Request) -> Iterator[Session]:
    session = request.app.state.sessionmaker()
    try:
        yield session
    finally:
        session.close()


def get_gateway(request: Request) -> FakeGateway:
    return request.app.state.gateway


def current_customer(x_customer_id: str = Header(min_length=1)) -> str:
    return x_customer_id


def require_staff(request: Request, x_staff_token: str = Header()) -> None:
    if not hmac.compare_digest(x_staff_token, request.app.state.staff_token):
        raise HTTPException(status_code=403, detail="staff only")
