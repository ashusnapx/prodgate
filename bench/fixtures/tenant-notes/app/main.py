from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.db import build_sessionmaker
from app.errors import Conflict, Forbidden, NotFound
from app.routers import exports, notes, shares, workspaces

PROBLEMS = {NotFound: (404, "Not found"), Forbidden: (403, "Forbidden"), Conflict: (409, "Conflict")}


def create_app(database_url: str = "sqlite:///./notes.db") -> FastAPI:
    app = FastAPI(title="Team notes")
    app.state.sessionmaker = build_sessionmaker(database_url)
    for module in (workspaces, notes, shares, exports):
        app.include_router(module.router)

    async def problem(_: Request, exc: Exception) -> JSONResponse:
        status, title = PROBLEMS[type(exc)]
        return JSONResponse(
            {"type": "about:blank", "title": title, "status": status, "detail": str(exc)},
            status_code=status,
            media_type="application/problem+json",
        )

    for exc_type in PROBLEMS:
        app.add_exception_handler(exc_type, problem)
    return app
