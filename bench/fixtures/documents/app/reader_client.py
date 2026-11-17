import base64
import logging

import httpx

from app.config import settings

log = logging.getLogger(__name__)


class ReaderClient:
    """Sends documents to the reader service.

    The reader answers later by calling POST /internal/readings/{id}/result or /error.
    """

    def __init__(self, base_url: str | None = None, token: str | None = None, timeout: float = 10.0):
        self.base_url = (base_url or settings.reader_url).rstrip("/")
        self.token = token or settings.reader_token
        self.timeout = timeout

    def submit(self, reading_id: int, content_type: str, data: bytes) -> None:
        body = {"reading_id": reading_id, "content_type": content_type, "content": base64.b64encode(data).decode()}
        try:
            resp = httpx.post(
                f"{self.base_url}/v1/read",
                json=body,
                headers={"Authorization": f"Bearer {self.token}"},
                timeout=self.timeout,
            )
            resp.raise_for_status()
        except httpx.HTTPError:
            log.exception("could not submit reading %s", reading_id)


class RecordingReader:
    """Stand-in for local runs and tests: remembers what was submitted."""

    def __init__(self):
        self.submitted: list[int] = []

    def submit(self, reading_id: int, content_type: str, data: bytes) -> None:
        self.submitted.append(reading_id)
