from datetime import datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.clock import utcnow
from app.models import Invoice, InvoiceKind, InvoiceStatus, Plan, PlanChange, Subscription, SubscriptionStatus
from app.services import catalog, invoices
from app.services.errors import Conflict, NotFound


def get_subscription(db: Session, account_id: str, sub_id: int) -> Subscription:
    sub = db.get(Subscription, sub_id)
    if sub is None or sub.account_id != account_id:
        raise NotFound(f"subscription {sub_id}")
    return sub


def create_subscription(db: Session, account_id: str, customer_ref: str, plan_code: str) -> tuple[Subscription, Invoice | None]:
    plan = catalog.get_plan(db, account_id, plan_code)
    now = utcnow()
    trial_end = now + timedelta(days=plan.trial_days) if plan.trial_days else None
    sub = Subscription(
        account_id=account_id,
        customer_ref=customer_ref,
        plan_id=plan.id,
        status=SubscriptionStatus.TRIALING if trial_end else SubscriptionStatus.ACTIVE,
        trial_ends_at=trial_end,
        current_period_start=now,
        current_period_end=trial_end or now + timedelta(days=plan.interval_days),
    )
    db.add(sub)
    db.flush()
    invoice = None
    if trial_end is None:
        invoice = invoices.new_invoice(sub, InvoiceKind.PERIOD, plan.price_cents, now, sub.current_period_end)
        db.add(invoice)
    db.commit()
    return sub, invoice


def cancel_subscription(db: Session, account_id: str, sub_id: int, at_period_end: bool) -> Subscription:
    """Cancel now (voiding unpaid invoices) or at the end of the current period or trial."""
    sub = get_subscription(db, account_id, sub_id)
    now = utcnow()
    query = update(Subscription).where(Subscription.id == sub.id, Subscription.status != SubscriptionStatus.CANCELED)
    if at_period_end:
        result = db.execute(query.values(cancel_at_period_end=True))
    else:
        result = db.execute(query.values(status=SubscriptionStatus.CANCELED, canceled_at=now, cancel_at_period_end=False))
        db.execute(
            update(Invoice)
            .where(Invoice.subscription_id == sub.id, Invoice.status.in_([InvoiceStatus.OPEN, InvoiceStatus.FAILED]))
            .values(status=InvoiceStatus.VOID)
        )
    if result.rowcount == 0:
        db.rollback()
        raise Conflict(f"subscription {sub_id} is already canceled")
    db.commit()
    db.refresh(sub)
    return sub


def proration_amount(old: Plan, new: Plan, start: datetime, end: datetime, now: datetime) -> int:
    """Price difference for the part of the period that is left, in cents (negative for a downgrade)."""
    total = (end - start).total_seconds()
    left = max((end - now).total_seconds(), 0.0)
    fraction = left / total if total > 0 else 0.0
    return round((new.price_cents - old.price_cents) * fraction)


def change_plan(db: Session, account_id: str, sub_id: int, plan_code: str, request_id: str) -> tuple[PlanChange, Invoice | None]:
    """Move to another plan now. Upgrades are charged the prorated difference; downgrades credit nothing."""
    sub = get_subscription(db, account_id, sub_id)
    previous = _previous_change(db, sub.id, request_id)
    if previous is not None:
        return previous
    if sub.status not in (SubscriptionStatus.TRIALING, SubscriptionStatus.ACTIVE):
        raise Conflict(f"subscription {sub_id} is {sub.status.value}")

    new_plan = db.scalar(select(Plan).where(Plan.code == plan_code))
    if new_plan is None:
        raise NotFound(f"plan {plan_code}")
    if new_plan.id == sub.plan_id:
        raise Conflict(f"subscription {sub_id} is already on {plan_code}")

    now = utcnow()
    invoice = None
    if sub.status == SubscriptionStatus.ACTIVE:
        amount = proration_amount(sub.plan, new_plan, sub.current_period_start, sub.current_period_end, now)
        if amount > 0:
            invoice = invoices.new_invoice(sub, InvoiceKind.PRORATION, amount, now, sub.current_period_end)
            db.add(invoice)
            db.flush()

    old_plan_id = sub.plan_id
    result = db.execute(
        update(Subscription).where(Subscription.id == sub.id, Subscription.plan_id == old_plan_id).values(plan_id=new_plan.id)
    )
    if result.rowcount == 0:
        db.rollback()
        return _previous_or_conflict(db, sub.id, request_id)
    db.add(
        PlanChange(
            subscription_id=sub.id, request_id=request_id, from_plan_id=old_plan_id, to_plan_id=new_plan.id,
            invoice_id=invoice.id if invoice else None,
        )
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return _previous_or_conflict(db, sub.id, request_id)
    db.refresh(sub)
    return _previous_change(db, sub.id, request_id)


def _previous_change(db: Session, sub_id: int, request_id: str) -> tuple[PlanChange, Invoice | None] | None:
    change = db.scalar(select(PlanChange).where(PlanChange.subscription_id == sub_id, PlanChange.request_id == request_id))
    if change is None:
        return None
    return change, db.get(Invoice, change.invoice_id) if change.invoice_id else None


def _previous_or_conflict(db: Session, sub_id: int, request_id: str) -> tuple[PlanChange, Invoice | None]:
    previous = _previous_change(db, sub_id, request_id)
    if previous is None:
        raise Conflict(f"subscription {sub_id} changed plan at the same time; try again")
    return previous
