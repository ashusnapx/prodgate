from datetime import timedelta

from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.deps import get_session, require_editor, require_live_member
from app.errors import NotFound
from app.models import Membership, ShareLink, utcnow
from app.schemas import SharedNoteOut, ShareIn, ShareOut
from app.services import notes, shares

router = APIRouter(tags=["shares"])


@router.post("/workspaces/{workspace_id}/notes/{note_id}/shares", status_code=201, response_model=ShareOut)
def create_share(
    note_id: int, body: ShareIn, member: Membership = Depends(require_editor), session: Session = Depends(get_session)
):
    note = notes.note_in_workspace(session, member.workspace_id, note_id)
    expires_in = timedelta(hours=body.expires_in_hours) if body.expires_in_hours else None
    return shares.create_share(session, note, member.user_id, expires_in)


@router.get("/workspaces/{workspace_id}/notes/{note_id}/shares", response_model=list[ShareOut])
def list_shares(note_id: int, member: Membership = Depends(require_live_member), session: Session = Depends(get_session)):
    note = notes.note_in_workspace(session, member.workspace_id, note_id)
    return shares.shares_for_note(session, note.id)


@router.delete("/workspaces/{workspace_id}/shares/{share_id}", response_model=ShareOut)
def revoke_share(share_id: int, member: Membership = Depends(require_editor), session: Session = Depends(get_session)):
    link = session.get(ShareLink, share_id)
    if link is None or link.note.workspace_id != member.workspace_id:
        raise NotFound(f"share {share_id}")
    return shares.revoke_share(session, link)


@router.get("/s/{token}", response_model=SharedNoteOut)
def view_shared_note(token: str, session: Session = Depends(get_session)):
    note = shares.resolve_share(session, token).note
    return SharedNoteOut(title=note.title, body=note.body, updated_at=note.updated_at)


@router.get("/s/{token}/raw", response_class=PlainTextResponse)
def download_shared_note(token: str, session: Session = Depends(get_session)):
    link = shares.find_by_token(session, token)
    if link is None or shares.is_expired(link, utcnow()) or link.note.deleted_at is not None:
        raise NotFound("share link")
    filename = f"note-{link.note_id}.md"
    return PlainTextResponse(
        shares.render_note_markdown(link.note),
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
