from datetime import datetime

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.clock import utcnow
from app.models import Invoice, InvoiceKind, InvoiceStatus, Payment, Subscription, SubscriptionStatus
from app.provider import PaymentProvider
from app.services.errors import Conflict, NotFound


def get_invoice(db: Session, account_id: str, invoice_id: int) -> Invoice:
    invoice = db.get(Invoice, invoice_id)
    if invoice is None or invoice.account_id != account_id:
        raise NotFound(f"invoice {invoice_id}")
    return invoice


def new_invoice(sub: Subscription, kind: InvoiceKind, amount_cents: int, start: datetime, end: datetime) -> Invoice:
    return Invoice(
        account_id=sub.account_id,
        subscription_id=sub.id,
        kind=kind,
        amount_cents=amount_cents,
        period_start=start,
        period_end=end,
    )


def pay_invoice(db: Session, provider: PaymentProvider, invoice: Invoice) -> Invoice:
    """Charge what is still owed on an open or failed invoice."""
    now = utcnow()
    result = db.execute(
        update(Invoice)
        .where(Invoice.id == invoice.id, Invoice.status.in_([InvoiceStatus.OPEN, InvoiceStatus.FAILED]))
        .values(status=InvoiceStatus.PENDING, charge_attempted_at=now, failure_reason=None)
    )
    if result.rowcount == 0:
        db.rollback()
        raise Conflict(f"invoice {invoice.id} is {invoice.status.value}")
    db.commit()
    db.refresh(invoice)

    charge = provider.create_charge(
        invoice.amount_cents - invoice.amount_paid_cents,
        idempotency_key=f"invoice-{invoice.id}-{now:%Y%m%d%H%M%S}",
        metadata={"invoice_id": invoice.id, "account_id": invoice.account_id},
    )
    invoice.charge_id = charge.id
    if charge.status == "succeeded":
        record_payment(db, invoice, charge.id, charge.amount_cents)
    elif charge.status == "failed":
        mark_payment_failed(db, invoice, charge.failure_reason or "payment failed")
    db.commit()
    return invoice


def record_payment(db: Session, invoice: Invoice, charge_id: str, amount_cents: int) -> None:
    db.add(Payment(invoice_id=invoice.id, charge_id=charge_id, amount_cents=amount_cents))
    db.execute(
        update(Invoice)
        .where(Invoice.id == invoice.id)
        .values(amount_paid_cents=Invoice.amount_paid_cents + amount_cents)
    )
    db.refresh(invoice)
    if invoice.amount_paid_cents >= invoice.amount_cents and invoice.status != InvoiceStatus.PAID:
        invoice.status = InvoiceStatus.PAID
        invoice.paid_at = utcnow()
        _mark_paid_up(invoice.subscription)


def _mark_paid_up(sub: Subscription) -> None:
    sub.status = SubscriptionStatus.ACTIVE


def mark_payment_failed(db: Session, invoice: Invoice, reason: str) -> None:
    invoice.status = InvoiceStatus.FAILED
    invoice.failure_reason = reason[:300]
    sub = invoice.subscription
    if sub.status == SubscriptionStatus.ACTIVE:
        sub.status = SubscriptionStatus.PAST_DUE
