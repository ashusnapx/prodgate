from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import Invoice, InvoiceStatus, Payment, Refund
from app.provider import PaymentProvider
from app.services.errors import Conflict
from app.services.invoices import get_invoice


def refund_invoice(db: Session, provider: PaymentProvider, account_id: str, invoice_id: int, amount_cents: int, idempotency_key: str) -> Refund:
    """Refund part or all of a paid invoice. Repeating a key returns the refund it made."""
    invoice = get_invoice(db, account_id, invoice_id)
    existing = db.scalar(select(Refund).where(Refund.invoice_id == invoice.id, Refund.idempotency_key == idempotency_key))
    if existing is not None:
        return existing

    if invoice.status != InvoiceStatus.PAID:
        raise Conflict(f"invoice {invoice_id} is {invoice.status.value}, not paid")
    refundable = invoice.amount_paid_cents - invoice.amount_refunded_cents
    if amount_cents > refundable:
        raise Conflict(f"only {refundable} cents can be refunded")

    payment = db.scalar(select(Payment).where(Payment.invoice_id == invoice.id).order_by(Payment.id.desc()).limit(1))
    issued = provider.refund(payment.charge_id, amount_cents)
    refund = Refund(invoice_id=invoice.id, amount_cents=amount_cents, idempotency_key=idempotency_key, provider_refund_id=issued.id)
    db.add(refund)
    db.execute(
        update(Invoice)
        .where(Invoice.id == invoice.id)
        .values(amount_refunded_cents=Invoice.amount_refunded_cents + amount_cents)
    )
    db.commit()
    return refund
