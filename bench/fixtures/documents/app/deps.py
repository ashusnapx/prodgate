import hmac

from fastapi import Header, HTTPException

from app.config import settings


def current_org(x_org_id: str = Header(min_length=1, max_length=64)) -> str:
    return x_org_id


def current_user(x_user_id: str = Header(min_length=1, max_length=100)) -> str:
    return x_user_id


def require_reader(authorization: str = Header()) -> None:
    expected = f"Bearer {settings.reader_token}"
    if not hmac.compare_digest(authorization, expected):
        raise HTTPException(status_code=401, detail="invalid reader token")
