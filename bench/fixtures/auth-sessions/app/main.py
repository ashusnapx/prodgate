from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app import models  # noqa: F401  (registers tables)
from app.config import settings
from app.db import make_session_factory
from app.routers import admin, auth, me
from app.services import errors

PROBLEMS = {
    errors.NotAuthenticated: (401, "Not signed in"),
    errors.InvalidCredentials: (401, "Wrong email or password"),
    errors.RateLimited: (429, "Too many attempts, wait a minute"),
    errors.InviteExpired: (403, "Your invite has expired; ask your admin for a new one"),
    errors.PasswordPolicyError: (422, "Password not accepted"),
    errors.NotFound: (404, "Not found"),
    errors.Conflict: (409, "Conflict"),
}


def create_app(database_url: str | None = None) -> FastAPI:
    app = FastAPI(title="auth-sessions")
    app.state.session_factory = make_session_factory(database_url or settings.database_url)

    app.include_router(auth.router)
    app.include_router(me.router)
    app.include_router(admin.router)

    for exc_type, (status, title) in PROBLEMS.items():

        def handler(request: Request, exc: Exception, status=status, title=title):
            body = {"type": "about:blank", "title": title, "status": status, "detail": str(exc) or title}
            return JSONResponse(body, status_code=status)

        app.add_exception_handler(exc_type, handler)

    return app
