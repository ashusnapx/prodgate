import json

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.errors import Conflict
from app.models import ExportJob, Note, utcnow
from app.services.shares import render_note_markdown

ACTIVE = ("queued", "running", "cancelling")


def start_export(session: Session, workspace_id: int, user_id: str, note_ids: list[int] | None) -> ExportJob:
    job = ExportJob(
        workspace_id=workspace_id,
        requested_by=user_id,
        note_ids=json.dumps(sorted(set(note_ids))) if note_ids else None,
    )
    session.add(job)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise Conflict(f"an export of workspace {workspace_id} is already in progress") from None
    return job


def cancel_export(session: Session, job: ExportJob) -> ExportJob:
    if job.status not in ("queued", "running"):
        raise Conflict(f"export {job.id} is {job.status}")
    job.status = "cancelling"
    session.commit()
    return job


def collect_notes(session: Session, job: ExportJob) -> list[Note]:
    query = select(Note).where(Note.deleted_at.is_(None)).order_by(Note.id)
    if job.note_ids:
        query = query.where(Note.id.in_(json.loads(job.note_ids)))
    else:
        query = query.where(Note.workspace_id == job.workspace_id)
    return list(session.scalars(query))


def render_export(workspace_name: str, notes: list[Note]) -> str:
    parts = [f"<!-- export of {workspace_name}, {len(notes)} notes -->\n"]
    parts.extend(render_note_markdown(note) for note in notes)
    return "\n".join(parts)


def _claim(session: Session, job_id: int) -> bool:
    claimed = session.execute(
        update(ExportJob)
        .where(ExportJob.id == job_id, ExportJob.status == "queued")
        .values(status="running", started_at=utcnow())
    )
    session.commit()
    return claimed.rowcount == 1


def run_export(make_session: sessionmaker[Session], job_id: int) -> None:
    with make_session() as session:
        if not _claim(session, job_id):
            return
        job = session.get(ExportJob, job_id)
        try:
            notes = collect_notes(session, job)
            job.result = render_export(job.workspace.name, notes)
            job.note_count = len(notes)
        except Exception as exc:
            session.rollback()
            job = session.get(ExportJob, job_id)
            job.status = "failed"
            job.error = str(exc)[:500]
            job.finished_at = utcnow()
            session.commit()
            return
        job.status = "done"
        job.finished_at = utcnow()
        session.commit()
