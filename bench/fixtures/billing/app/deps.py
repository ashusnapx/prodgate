import hmac

from fastapi import Header, HTTPException, Request

from app.config import settings
from app.provider import PaymentProvider


def current_account(x_account_id: str = Header(min_length=1, max_length=64)) -> str:
    return x_account_id


def provider(request: Request) -> PaymentProvider:
    return request.app.state.provider


def require_cron(x_cron_token: str = Header()) -> None:
    if not hmac.compare_digest(x_cron_token, settings.cron_token):
        raise HTTPException(status_code=401, detail="invalid cron token")
