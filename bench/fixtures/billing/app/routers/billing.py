import json

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import current_account, provider, require_cron
from app.models import InvoiceStatus
from app.provider import PaymentProvider
from app.schemas import (CancelRequest, ChangePlanOut, ChangePlanRequest, InvoiceOut, PlanCreate,
                         PlanOut, RefundOut, RefundRequest, SubscriptionCreate, SubscriptionOut)
from app.services import catalog, cycle, invoices, refunds, subscriptions, webhooks

router = APIRouter(tags=["billing"])


@router.post("/plans", response_model=PlanOut, status_code=status.HTTP_201_CREATED)
def create_plan(body: PlanCreate, account: str = Depends(current_account), db: Session = Depends(get_db)):
    return catalog.create_plan(db, account, body.code, body.name, body.price_cents, body.interval_days, body.trial_days)


@router.post("/subscriptions", response_model=SubscriptionOut, status_code=status.HTTP_201_CREATED)
def create_subscription(
    body: SubscriptionCreate,
    account: str = Depends(current_account),
    db: Session = Depends(get_db),
    payments: PaymentProvider = Depends(provider),
):
    sub, first_invoice = subscriptions.create_subscription(db, account, body.customer_ref, body.plan_code)
    if first_invoice is not None:
        invoices.pay_invoice(db, payments, first_invoice)
        db.refresh(sub)
    return sub


@router.get("/subscriptions/{sub_id}", response_model=SubscriptionOut)
def get_subscription(sub_id: int, account: str = Depends(current_account), db: Session = Depends(get_db)):
    return subscriptions.get_subscription(db, account, sub_id)


@router.get("/subscriptions/{sub_id}/invoices", response_model=list[InvoiceOut])
def list_invoices(sub_id: int, account: str = Depends(current_account), db: Session = Depends(get_db)):
    return subscriptions.get_subscription(db, account, sub_id).invoices


@router.post("/subscriptions/{sub_id}/cancel", response_model=SubscriptionOut)
def cancel(sub_id: int, body: CancelRequest, account: str = Depends(current_account), db: Session = Depends(get_db)):
    return subscriptions.cancel_subscription(db, account, sub_id, at_period_end=body.at_period_end)


@router.post("/subscriptions/{sub_id}/change-plan", response_model=ChangePlanOut)
def change_plan(
    sub_id: int,
    body: ChangePlanRequest,
    account: str = Depends(current_account),
    db: Session = Depends(get_db),
    payments: PaymentProvider = Depends(provider),
):
    _, invoice = subscriptions.change_plan(db, account, sub_id, body.plan_code, body.request_id)
    if invoice is not None and invoice.status == InvoiceStatus.OPEN:
        invoices.pay_invoice(db, payments, invoice)
    sub = subscriptions.get_subscription(db, account, sub_id)
    db.refresh(sub)
    return ChangePlanOut(subscription=sub, proration_invoice=invoice)


@router.get("/invoices/{invoice_id}", response_model=InvoiceOut)
def get_invoice(invoice_id: int, account: str = Depends(current_account), db: Session = Depends(get_db)):
    return invoices.get_invoice(db, account, invoice_id)


@router.post("/invoices/{invoice_id}/pay", response_model=InvoiceOut)
def pay(invoice_id: int, account: str = Depends(current_account), db: Session = Depends(get_db), payments: PaymentProvider = Depends(provider)):
    return invoices.pay_invoice(db, payments, invoices.get_invoice(db, account, invoice_id))


@router.post("/invoices/{invoice_id}/refunds", response_model=RefundOut, status_code=status.HTTP_201_CREATED)
def refund(
    invoice_id: int,
    body: RefundRequest,
    idempotency_key: str = Header(min_length=8, max_length=200),
    account: str = Depends(current_account),
    db: Session = Depends(get_db),
    payments: PaymentProvider = Depends(provider),
):
    return refunds.refund_invoice(db, payments, account, invoice_id, body.amount_cents, idempotency_key)


@router.post("/webhooks/provider")
async def provider_webhook(request: Request, x_signature: str | None = Header(default=None), db: Session = Depends(get_db)):
    body = await request.body()
    if not webhooks.verify_signature(body, x_signature):
        raise HTTPException(status_code=401, detail="bad signature")
    return {"result": webhooks.handle_event(db, json.loads(body))}


@router.post("/jobs/billing-cycle", dependencies=[Depends(require_cron)])
def billing_cycle(db: Session = Depends(get_db), payments: PaymentProvider = Depends(provider)):
    return cycle.run_billing_cycle(db, payments)
