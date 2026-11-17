from fastapi import APIRouter, BackgroundTasks, Depends, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.deps import get_session, require_live_member
from app.errors import Conflict, NotFound
from app.models import ExportJob, Membership
from app.schemas import ExportIn, ExportOut
from app.services import exports

router = APIRouter(prefix="/workspaces/{workspace_id}/exports", tags=["exports"])


def _job(session: Session, workspace_id: int, export_id: int) -> ExportJob:
    job = session.get(ExportJob, export_id)
    if job is None or job.workspace_id != workspace_id:
        raise NotFound(f"export {export_id}")
    return job


@router.post("", status_code=202, response_model=ExportOut)
def start_export(
    body: ExportIn,
    request: Request,
    background: BackgroundTasks,
    member: Membership = Depends(require_live_member),
    session: Session = Depends(get_session),
):
    job = exports.start_export(session, member.workspace_id, member.user_id, body.note_ids)
    background.add_task(exports.run_export, request.app.state.sessionmaker, job.id)
    return job


@router.get("/{export_id}", response_model=ExportOut)
def show_export(export_id: int, member: Membership = Depends(require_live_member), session: Session = Depends(get_session)):
    return _job(session, member.workspace_id, export_id)


@router.delete("/{export_id}", response_model=ExportOut)
def cancel_export(export_id: int, member: Membership = Depends(require_live_member), session: Session = Depends(get_session)):
    return exports.cancel_export(session, _job(session, member.workspace_id, export_id))


@router.get("/{export_id}/download", response_class=PlainTextResponse)
def download_export(
    export_id: int, member: Membership = Depends(require_live_member), session: Session = Depends(get_session)
):
    job = _job(session, member.workspace_id, export_id)
    if job.status != "done":
        raise Conflict(f"export {export_id} is {job.status}")
    return PlainTextResponse(job.result, media_type="text/markdown")
