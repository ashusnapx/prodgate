import hmac

from fastapi import Header, HTTPException

from app.config import settings


def current_tenant(x_tenant_id: str = Header(min_length=1, max_length=64)) -> str:
    return x_tenant_id


def require_worker(x_worker_token: str = Header()) -> None:
    if not hmac.compare_digest(x_worker_token, settings.worker_token):
        raise HTTPException(status_code=401, detail="invalid worker token")
