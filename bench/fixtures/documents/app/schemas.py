from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models import DocumentStatus, ReadingState

CODE_PATTERN = r"^[a-z0-9][a-z0-9-]{1,62}$"


class ProjectCreate(BaseModel):
    code: str = Field(pattern=CODE_PATTERN)
    name: str = Field(min_length=1, max_length=200)


class ProjectRename(BaseModel):
    code: str = Field(pattern=CODE_PATTERN)
    name: str = Field(min_length=1, max_length=200)


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    created_at: datetime


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_code: str
    filename: str
    content_type: str
    size: int
    content_hash: str
    status: DocumentStatus
    uploaded_by: str
    created_at: datetime
    updated_at: datetime
    withdrawn_at: datetime | None


class UploadOut(BaseModel):
    document: DocumentOut
    duplicate: bool
    reading_id: int | None


class ReadingSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    document_id: int
    version: int
    state: ReadingState
    is_current: bool
    page_count: int | None
    error: str | None
    started_at: datetime
    finished_at: datetime | None


class ReadingOut(ReadingSummary):
    text: str | None


class ReaderResult(BaseModel):
    text: str
    page_count: int | None = Field(default=None, ge=0)


class ReaderError(BaseModel):
    error: str = Field(min_length=1)


class SearchHit(BaseModel):
    document_id: int
    filename: str
    reading_id: int
    snippet: str
