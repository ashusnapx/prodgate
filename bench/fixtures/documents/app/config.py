import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Settings:
    database_url: str = field(default_factory=lambda: os.environ.get("DOCS_DATABASE_URL", "sqlite:///./documents.db"))
    reader_url: str = field(default_factory=lambda: os.environ.get("DOCS_READER_URL", "http://reader.internal:8080"))
    reader_token: str = field(default_factory=lambda: os.environ.get("DOCS_READER_TOKEN", "dev-reader-token"))
    max_upload_bytes: int = 20 * 1024 * 1024
    reading_timeout_minutes: int = 30


settings = Settings()
