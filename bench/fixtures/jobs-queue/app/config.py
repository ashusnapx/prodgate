import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Settings:
    database_url: str = field(default_factory=lambda: os.environ.get("JOBS_DATABASE_URL", "sqlite:///./jobs.db"))
    worker_token: str = field(default_factory=lambda: os.environ.get("JOBS_WORKER_TOKEN", "dev-worker-token"))
    heartbeat_timeout_seconds: int = 90
    retry_base_seconds: int = 10
    retry_max_seconds: int = 3600
    default_max_attempts: int = 5
    callback_queue: str = "callbacks"


settings = Settings()
