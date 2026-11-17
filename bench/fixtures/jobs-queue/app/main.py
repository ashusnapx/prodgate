from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app import models  # noqa: F401  (registers tables)
from app.config import settings
from app.db import make_session_factory
from app.routers import batches as batches_router
from app.routers import jobs as jobs_router
from app.routers import worker as worker_router
from app.services.batches import BatchNotFound
from app.services.jobs import InvalidJobState, JobNotFound, LeaseLost


def _problem(status: int, title: str, detail: str) -> JSONResponse:
    return JSONResponse({"type": "about:blank", "title": title, "status": status, "detail": detail}, status_code=status)


def create_app(database_url: str | None = None) -> FastAPI:
    app = FastAPI(title="jobs-queue")
    app.state.session_factory = make_session_factory(database_url or settings.database_url)

    app.include_router(jobs_router.router)
    app.include_router(batches_router.router)
    app.include_router(worker_router.router)

    @app.exception_handler(JobNotFound)
    def _job_not_found(request: Request, exc: JobNotFound):
        return _problem(404, "Job not found", f"job {exc.args[0]} does not exist")

    @app.exception_handler(BatchNotFound)
    def _batch_not_found(request: Request, exc: BatchNotFound):
        return _problem(404, "Batch not found", f"batch {exc.args[0]} does not exist")

    @app.exception_handler(LeaseLost)
    def _lease_lost(request: Request, exc: LeaseLost):
        return _problem(409, "Lease lost", f"worker no longer holds job {exc.args[0]}")

    @app.exception_handler(InvalidJobState)
    def _invalid_state(request: Request, exc: InvalidJobState):
        return _problem(409, "Invalid job state", str(exc))

    @app.get("/health")
    def health():
        return {"ok": True}

    return app
