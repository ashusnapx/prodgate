import json
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models import BatchStatus, JobStatus


class JobSpec(BaseModel):
    queue: str = Field(min_length=1, max_length=64)
    kind: str = Field(min_length=1, max_length=100)
    payload: dict[str, Any] = Field(default_factory=dict)
    priority: int = 0
    max_attempts: int | None = Field(default=None, ge=1, le=50)
    run_after: datetime | None = None


class JobCreate(JobSpec):
    idempotency_key: str | None = Field(default=None, max_length=200)


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    queue: str
    kind: str
    payload: dict[str, Any]
    priority: int
    status: JobStatus
    attempts: int
    max_attempts: int
    run_after: datetime
    batch_id: int | None
    lease_owner: str | None
    last_error: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None

    @field_validator("payload", mode="before")
    @classmethod
    def _decode_payload(cls, value: Any) -> Any:
        return json.loads(value) if isinstance(value, str) else value


class JobOutputOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    data: dict[str, Any]
    created_at: datetime

    @field_validator("data", mode="before")
    @classmethod
    def _decode(cls, value: Any) -> Any:
        return json.loads(value) if isinstance(value, str) else value


class CancelRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


class BatchCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    jobs: list[JobSpec] = Field(min_length=1, max_length=1000)
    callback_url: str | None = Field(default=None, max_length=500)


class BatchOut(BaseModel):
    id: int
    name: str
    status: BatchStatus
    total_jobs: int
    counts: dict[str, int]
    created_at: datetime
    finished_at: datetime | None


class ClaimRequest(BaseModel):
    queue: str
    worker_id: str = Field(min_length=1, max_length=100)


class WorkerRequest(BaseModel):
    worker_id: str = Field(min_length=1, max_length=100)


class CompleteRequest(WorkerRequest):
    output: dict[str, Any] | None = None


class FailRequest(WorkerRequest):
    error: str = Field(min_length=1)
    retryable: bool = True
