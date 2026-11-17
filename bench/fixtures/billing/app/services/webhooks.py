import hashlib
import hmac
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Invoice, WebhookEvent
from app.services import invoices


def verify_signature(body: bytes, header: str | None) -> bool:
    if not header or not header.startswith("sha256="):
        return False
    expected = hmac.new(settings.webhook_secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(header.removeprefix("sha256="), expected)


def handle_event(db: Session, event: dict[str, Any]) -> str:
    """Apply a provider event once. The provider retries until it gets a 2xx, so repeats are normal."""
    if db.get(WebhookEvent, event["id"]) is not None:
        return "duplicate"
    try:
        db.add(WebhookEvent(id=event["id"], type=event["type"]))
        handler = HANDLERS.get(event["type"])
        if handler is not None:
            handler(db, event["data"])
        db.commit()
    except IntegrityError:
        db.rollback()
        return "duplicate"
    return "processed"


def _invoice_for(db: Session, data: dict[str, Any]) -> Invoice | None:
    invoice_id = (data.get("metadata") or {}).get("invoice_id")
    return db.get(Invoice, int(invoice_id)) if invoice_id is not None else None


def on_payment_succeeded(db: Session, data: dict[str, Any]) -> None:
    invoice = _invoice_for(db, data)
    if invoice is None:
        return
    if invoice.charge_id is None:
        invoice.charge_id = data["charge_id"]
    invoices.record_payment(db, invoice, data["charge_id"], int(data["amount_cents"]))


def on_payment_failed(db: Session, data: dict[str, Any]) -> None:
    invoice = _invoice_for(db, data)
    if invoice is None:
        return
    invoices.mark_payment_failed(db, invoice, data.get("failure_reason") or "payment failed")


HANDLERS = {
    "payment.succeeded": on_payment_succeeded,
    "payment.failed": on_payment_failed,
}
