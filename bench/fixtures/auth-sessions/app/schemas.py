from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models import InviteStatus, Role, UserStatus


class SignInRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=200)


class SignInResponse(BaseModel):
    token: str
    must_set_password: bool


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    org_id: str
    email: str
    display_name: str
    role: Role
    status: UserStatus
    must_set_password: bool


class SessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_agent: str | None
    created_at: datetime
    last_seen_at: datetime
    expires_at: datetime


class SetPasswordRequest(BaseModel):
    current_password: str | None = Field(default=None, max_length=200)
    new_password: str = Field(max_length=200)


class InviteRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    display_name: str = Field(min_length=1, max_length=200)
    role: Role = Role.MEMBER


class InviteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    email: str
    status: InviteStatus
    expires_at: datetime


class InviteCreated(BaseModel):
    invite: InviteOut
    temporary_password: str


class ResetOut(BaseModel):
    temporary_password: str
