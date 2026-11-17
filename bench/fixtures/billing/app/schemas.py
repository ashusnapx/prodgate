from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models import InvoiceKind, InvoiceStatus, SubscriptionStatus


class PlanCreate(BaseModel):
    code: str = Field(pattern=r"^[a-z0-9-]{2,64}$")
    name: str = Field(min_length=1, max_length=200)
    price_cents: int = Field(ge=0)
    interval_days: int = Field(default=30, ge=1, le=366)
    trial_days: int = Field(default=0, ge=0, le=90)


class PlanOut(PlanCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int


class SubscriptionCreate(BaseModel):
    customer_ref: str = Field(min_length=1, max_length=100)
    plan_code: str


class SubscriptionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    customer_ref: str
    plan_id: int
    status: SubscriptionStatus
    trial_ends_at: datetime | None
    current_period_start: datetime
    current_period_end: datetime
    cancel_at_period_end: bool
    canceled_at: datetime | None


class CancelRequest(BaseModel):
    at_period_end: bool = True


class ChangePlanRequest(BaseModel):
    plan_code: str
    request_id: str = Field(min_length=8, max_length=200)


class InvoiceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    subscription_id: int
    kind: InvoiceKind
    amount_cents: int
    amount_paid_cents: int
    amount_refunded_cents: int
    status: InvoiceStatus
    period_start: datetime
    period_end: datetime
    failure_reason: str | None
    paid_at: datetime | None


class ChangePlanOut(BaseModel):
    subscription: SubscriptionOut
    proration_invoice: InvoiceOut | None


class RefundRequest(BaseModel):
    amount_cents: int = Field(gt=0)


class RefundOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    invoice_id: int
    amount_cents: int
    created_at: datetime
