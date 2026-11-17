from datetime import datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.clock import utcnow
from app.config import settings
from app.models import Invoice, InvoiceKind, InvoiceStatus, Subscription, SubscriptionStatus
from app.provider import PaymentProvider, ProviderError
from app.services import invoices
from app.services.errors import Conflict


def end_trials(db: Session, now: datetime) -> list[int]:
    """Start the first paid period of every trial that has ended."""
    started = []
    trials = list(db.scalars(select(Subscription).where(Subscription.status == SubscriptionStatus.TRIALING, Subscription.trial_ends_at <= now)))
    for sub in trials:
        start = sub.trial_ends_at
        end = start + timedelta(days=sub.plan.interval_days)
        result = db.execute(
            update(Subscription)
            .where(Subscription.id == sub.id, Subscription.status == SubscriptionStatus.TRIALING)
            .values(status=SubscriptionStatus.ACTIVE, current_period_start=start, current_period_end=end)
        )
        if result.rowcount == 0:
            db.rollback()
            continue
        db.add(invoices.new_invoice(sub, InvoiceKind.PERIOD, sub.plan.price_cents, start, end))
        db.commit()
        started.append(sub.id)
    return started


def renew_due(db: Session, now: datetime) -> list[int]:
    """Roll active subscriptions into their next period, or cancel those set to cancel at period end."""
    renewed = []
    due = list(db.scalars(select(Subscription).where(Subscription.status == SubscriptionStatus.ACTIVE, Subscription.current_period_end <= now)))
    for sub in due:
        start = sub.current_period_end
        guard = update(Subscription).where(
            Subscription.id == sub.id,
            Subscription.status == SubscriptionStatus.ACTIVE,
            Subscription.current_period_end == start,
        )
        if sub.cancel_at_period_end:
            db.execute(guard.values(status=SubscriptionStatus.CANCELED, canceled_at=now))
            db.commit()
            continue
        end = start + timedelta(days=sub.plan.interval_days)
        result = db.execute(guard.values(current_period_start=start, current_period_end=end))
        if result.rowcount == 0:
            db.rollback()
            continue
        db.add(invoices.new_invoice(sub, InvoiceKind.PERIOD, sub.plan.price_cents, start, end))
        db.commit()
        renewed.append(sub.id)
    return renewed


def collect_open(db: Session, provider: PaymentProvider) -> list[int]:
    charged = []
    for invoice in list(db.scalars(select(Invoice).where(Invoice.status == InvoiceStatus.OPEN).order_by(Invoice.id))):
        try:
            invoices.pay_invoice(db, provider, invoice)
        except (ProviderError, Conflict):
            continue
        charged.append(invoice.id)
    return charged


def reconcile_pending(db: Session, provider: PaymentProvider, now: datetime) -> list[int]:
    """Settle charges whose webhook never came, by asking the provider."""
    settled = []
    cutoff = now - settings.reconcile_after
    stale = list(
        db.scalars(
            select(Invoice).where(
                Invoice.status == InvoiceStatus.PENDING,
                Invoice.charge_id.is_not(None),
                Invoice.charge_attempted_at < cutoff,
            )
        )
    )
    for invoice in stale:
        try:
            charge = provider.get_charge(invoice.charge_id)
        except ProviderError:
            continue
        if charge.status == "succeeded":
            invoices.record_payment(db, invoice, charge.id, charge.amount_cents)
        elif charge.status == "failed":
            invoices.mark_payment_failed(db, invoice, charge.failure_reason or "payment failed")
        else:
            continue
        db.commit()
        settled.append(invoice.id)
    return settled


def run_billing_cycle(db: Session, provider: PaymentProvider) -> dict[str, list[int]]:
    now = utcnow()
    return {
        "trials_ended": end_trials(db, now),
        "renewed": renew_due(db, now),
        "charged": collect_open(db, provider),
        "reconciled": reconcile_pending(db, provider, now),
    }
