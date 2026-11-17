from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app import models  # noqa: F401  (registers tables)
from app.config import settings
from app.db import make_session_factory
from app.provider import FakeProvider, ProviderError
from app.routers import billing
from app.services.errors import Conflict, NotFound


def _problem(status: int, title: str, detail: str) -> JSONResponse:
    return JSONResponse({"type": "about:blank", "title": title, "status": status, "detail": detail}, status_code=status)


def create_app(database_url: str | None = None, provider=None) -> FastAPI:
    app = FastAPI(title="billing")
    app.state.session_factory = make_session_factory(database_url or settings.database_url)
    app.state.provider = provider or FakeProvider()

    app.include_router(billing.router)

    @app.exception_handler(NotFound)
    def _not_found(request: Request, exc: NotFound):
        return _problem(404, "Not found", str(exc))

    @app.exception_handler(Conflict)
    def _conflict(request: Request, exc: Conflict):
        return _problem(409, "Conflict", str(exc))

    @app.exception_handler(ProviderError)
    def _provider(request: Request, exc: ProviderError):
        return _problem(502, "Payment provider unavailable", str(exc))

    return app
