from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.deps import can_edit, get_session, require_editor, require_live_member, require_member
from app.errors import Forbidden
from app.models import Membership
from app.schemas import NoteEdit, NoteIn, NoteOut
from app.services import notes

router = APIRouter(prefix="/workspaces/{workspace_id}", tags=["notes"])


@router.get("/notes", response_model=list[NoteOut])
def list_notes(
    q: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    before_id: int | None = None,
    member: Membership = Depends(require_live_member),
    session: Session = Depends(get_session),
):
    return notes.list_notes(session, member.workspace_id, q, limit, before_id)


@router.post("/notes", response_model=NoteOut, status_code=201)
def create_note(
    body: NoteIn,
    response: Response,
    member: Membership = Depends(require_editor),
    session: Session = Depends(get_session),
):
    note, created = notes.create_note(
        session, member.workspace_id, member.user_id, body.title, body.body, body.request_id
    )
    if not created:
        response.status_code = 200
    return note


@router.get("/notes/{note_id}", response_model=NoteOut)
def show_note(note_id: int, member: Membership = Depends(require_live_member), session: Session = Depends(get_session)):
    return notes.note_in_workspace(session, member.workspace_id, note_id)


@router.patch("/notes/{note_id}", response_model=NoteOut)
def edit_note(
    note_id: int, body: NoteEdit, member: Membership = Depends(require_editor), session: Session = Depends(get_session)
):
    note = notes.note_in_workspace(session, member.workspace_id, note_id)
    return notes.update_note(session, note, member.user_id, body.base_version, body.title, body.body)


@router.delete("/notes/{note_id}", status_code=204)
def delete_note(note_id: int, member: Membership = Depends(require_editor), session: Session = Depends(get_session)):
    notes.delete_note(session, notes.note_in_workspace(session, member.workspace_id, note_id))
    return Response(status_code=204)


@router.get("/trash", response_model=list[NoteOut])
def list_trash(member: Membership = Depends(require_member), session: Session = Depends(get_session)):
    return notes.list_trash(session, member.workspace_id)


@router.post("/trash/{note_id}/restore", response_model=NoteOut)
def restore_note(note_id: int, member: Membership = Depends(require_member), session: Session = Depends(get_session)):
    if not can_edit(member):
        raise Forbidden("editors only")
    note = notes.note_in_workspace(session, member.workspace_id, note_id, include_deleted=True)
    return notes.restore_note(session, note, member.user_id)
