from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import current_org, current_user
from app.schemas import DocumentOut, ProjectCreate, ProjectOut, ProjectRename, SearchHit, UploadOut
from app.services import documents, projects, readings

router = APIRouter(prefix="/projects", tags=["projects"])


@router.post("", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
def create_project(body: ProjectCreate, org: str = Depends(current_org), db: Session = Depends(get_db)):
    return projects.create_project(db, org, body.code, body.name)


@router.get("", response_model=list[ProjectOut])
def list_projects(org: str = Depends(current_org), db: Session = Depends(get_db)):
    return projects.list_projects(db, org)


@router.patch("/{code}", response_model=ProjectOut)
def rename_project(code: str, body: ProjectRename, org: str = Depends(current_org), db: Session = Depends(get_db)):
    return projects.rename_project(db, org, code, body.code, body.name)


@router.get("/{code}/documents", response_model=list[DocumentOut])
def list_documents(code: str, include_withdrawn: bool = False, org: str = Depends(current_org), db: Session = Depends(get_db)):
    projects.get_project(db, org, code)
    return documents.list_documents(db, org, code, include_withdrawn=include_withdrawn)


@router.post("/{code}/documents", response_model=UploadOut, status_code=status.HTTP_201_CREATED)
async def upload_document(
    code: str,
    request: Request,
    background: BackgroundTasks,
    filename: str = Query(min_length=1, max_length=255),
    org: str = Depends(current_org),
    user: str = Depends(current_user),
    db: Session = Depends(get_db),
):
    data = await request.body()
    content_type = request.headers.get("content-type", "application/octet-stream").split(";")[0].strip()
    doc, reading = documents.upload_document(db, org, code, filename, content_type, data, uploaded_by=user)
    if reading is not None:
        background.add_task(request.app.state.reader.submit, reading.id, content_type, data)
    return UploadOut(document=DocumentOut.model_validate(doc), duplicate=reading is None, reading_id=reading.id if reading else None)


@router.get("/{code}/search", response_model=list[SearchHit])
def search(code: str, q: str = Query(min_length=2, max_length=200), org: str = Depends(current_org), db: Session = Depends(get_db)):
    projects.get_project(db, org, code)
    hits = []
    for doc, reading in readings.search(db, org, code, q):
        at = (reading.text or "").lower().find(q.lower())
        start = max(at - 60, 0)
        hits.append(SearchHit(document_id=doc.id, filename=doc.filename, reading_id=reading.id, snippet=reading.text[start : at + len(q) + 60]))
    return hits
