import os
from dataclasses import dataclass, field
from datetime import timedelta


@dataclass(frozen=True)
class Settings:
    database_url: str = field(default_factory=lambda: os.environ.get("AUTH_DATABASE_URL", "sqlite:///./auth.db"))
    session_idle: timedelta = timedelta(hours=12)
    session_renew_after: timedelta = timedelta(minutes=15)
    invite_valid_for: timedelta = timedelta(days=7)
    sign_in_window: timedelta = timedelta(minutes=1)
    sign_in_max_attempts: int = 5
    min_password_length: int = 12


settings = Settings()
