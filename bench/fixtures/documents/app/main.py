from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app import models  # noqa: F401  (registers tables)
from app.config import settings
from app.db import make_session_factory
from app.reader_client import ReaderClient
from app.routers import documents, internal, projects
from app.services.errors import Conflict, InvalidUpload, NotFound


def _problem(status: int, title: str, detail: str) -> JSONResponse:
    return JSONResponse({"type": "about:blank", "title": title, "status": status, "detail": detail}, status_code=status)


def create_app(database_url: str | None = None, reader=None) -> FastAPI:
    app = FastAPI(title="documents")
    app.state.session_factory = make_session_factory(database_url or settings.database_url)
    app.state.reader = reader or ReaderClient()

    app.include_router(projects.router)
    app.include_router(documents.router)
    app.include_router(internal.router)

    @app.exception_handler(NotFound)
    def _not_found(request: Request, exc: NotFound):
        return _problem(404, "Not found", str(exc))

    @app.exception_handler(Conflict)
    def _conflict(request: Request, exc: Conflict):
        return _problem(409, "Conflict", str(exc))

    @app.exception_handler(InvalidUpload)
    def _invalid(request: Request, exc: InvalidUpload):
        return _problem(422, "Invalid upload", str(exc))

    return app
