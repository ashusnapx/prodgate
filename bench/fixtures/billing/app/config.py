import os
from dataclasses import dataclass, field
from datetime import timedelta


@dataclass(frozen=True)
class Settings:
    database_url: str = field(default_factory=lambda: os.environ.get("BILLING_DATABASE_URL", "sqlite:///./billing.db"))
    webhook_secret: str = field(default_factory=lambda: os.environ.get("BILLING_WEBHOOK_SECRET", "dev-webhook-secret"))
    cron_token: str = field(default_factory=lambda: os.environ.get("BILLING_CRON_TOKEN", "dev-cron-token"))
    reconcile_after: timedelta = timedelta(hours=1)


settings = Settings()
