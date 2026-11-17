from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class WorkspaceIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class WorkspaceOut(ORMModel):
    id: int
    name: str
    deleted_at: datetime | None


class MemberIn(BaseModel):
    user_id: str = Field(min_length=1, max_length=64)
    role: Literal["owner", "editor", "viewer"] = "editor"


class MemberOut(ORMModel):
    workspace_id: int
    user_id: str
    role: str


class NoteIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(default="", max_length=100_000)
    request_id: str | None = Field(default=None, max_length=64)


class NoteEdit(BaseModel):
    base_version: int
    title: str | None = Field(default=None, min_length=1, max_length=200)
    body: str | None = Field(default=None, max_length=100_000)


class NoteOut(ORMModel):
    id: int
    workspace_id: int
    title: str
    body: str
    version: int
    created_by: str
    updated_by: str
    updated_at: datetime
    deleted_at: datetime | None


class ShareIn(BaseModel):
    expires_in_hours: int | None = Field(default=None, gt=0, le=24 * 90)


class ShareOut(ORMModel):
    id: int
    note_id: int
    token: str
    expires_at: datetime | None
    revoked_at: datetime | None


class SharedNoteOut(BaseModel):
    title: str
    body: str
    updated_at: datetime


class ExportIn(BaseModel):
    note_ids: list[int] | None = Field(default=None, max_length=500)


class ExportOut(ORMModel):
    id: int
    workspace_id: int
    status: str
    note_count: int
    error: str | None
    created_at: datetime
    finished_at: datetime | None
