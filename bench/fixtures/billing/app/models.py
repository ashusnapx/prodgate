import enum
from datetime import datetime

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.clock import utcnow
from app.db import Base


class SubscriptionStatus(str, enum.Enum):
    TRIALING = "trialing"
    ACTIVE = "active"
    PAST_DUE = "past_due"
    CANCELED = "canceled"


class InvoiceStatus(str, enum.Enum):
    OPEN = "open"
    PENDING = "pending"
    PAID = "paid"
    FAILED = "failed"
    VOID = "void"


class InvoiceKind(str, enum.Enum):
    PERIOD = "period"
    PRORATION = "proration"


class Plan(Base):
    __tablename__ = "plans"
    __table_args__ = (UniqueConstraint("account_id", "code", name="uq_plans_account_code"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[str] = mapped_column(String(64), index=True)
    code: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(200))
    price_cents: Mapped[int]
    interval_days: Mapped[int] = mapped_column(default=30)
    trial_days: Mapped[int] = mapped_column(default=0)


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[str] = mapped_column(String(64), index=True)
    customer_ref: Mapped[str] = mapped_column(String(100), index=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("plans.id"))
    status: Mapped[SubscriptionStatus]
    trial_ends_at: Mapped[datetime | None]
    current_period_start: Mapped[datetime]
    current_period_end: Mapped[datetime]
    cancel_at_period_end: Mapped[bool] = mapped_column(default=False)
    canceled_at: Mapped[datetime | None]

    plan: Mapped[Plan] = relationship()
    invoices: Mapped[list["Invoice"]] = relationship(back_populates="subscription", order_by="Invoice.id")


class Invoice(Base):
    __tablename__ = "invoices"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[str] = mapped_column(String(64), index=True)
    subscription_id: Mapped[int] = mapped_column(ForeignKey("subscriptions.id"), index=True)
    kind: Mapped[InvoiceKind]
    amount_cents: Mapped[int]
    amount_paid_cents: Mapped[int] = mapped_column(default=0)
    amount_refunded_cents: Mapped[int] = mapped_column(default=0)
    status: Mapped[InvoiceStatus] = mapped_column(default=InvoiceStatus.OPEN)
    period_start: Mapped[datetime]
    period_end: Mapped[datetime]
    charge_id: Mapped[str | None] = mapped_column(String(100), index=True)
    charge_attempted_at: Mapped[datetime | None]
    failure_reason: Mapped[str | None] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    paid_at: Mapped[datetime | None]

    subscription: Mapped[Subscription] = relationship(back_populates="invoices")


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id"), index=True)
    charge_id: Mapped[str] = mapped_column(String(100))
    amount_cents: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class Refund(Base):
    __tablename__ = "refunds"

    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id"), index=True)
    amount_cents: Mapped[int]
    idempotency_key: Mapped[str] = mapped_column(String(200))
    provider_refund_id: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class PlanChange(Base):
    __tablename__ = "plan_changes"
    __table_args__ = (UniqueConstraint("subscription_id", "request_id", name="uq_plan_changes_request"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    subscription_id: Mapped[int] = mapped_column(ForeignKey("subscriptions.id"))
    request_id: Mapped[str] = mapped_column(String(200))
    from_plan_id: Mapped[int]
    to_plan_id: Mapped[int]
    invoice_id: Mapped[int | None]


class WebhookEvent(Base):
    __tablename__ = "webhook_events"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    type: Mapped[str] = mapped_column(String(64))
    received_at: Mapped[datetime] = mapped_column(default=utcnow)
