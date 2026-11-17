from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Order, Payment, Refund, ReturnLine, ReturnRequest, utcnow
from app.services import stock
from app.services.orders import DELIVERED, NotFound
from app.services.payments import FakeGateway

RETURN_WINDOW = timedelta(days=30)
REQUESTED = "requested"
APPROVED = "approved"
REJECTED = "rejected"


class ReturnError(Exception):
    """The return cannot be created or decided in its current state."""


def get_return(session: Session, return_id: int) -> ReturnRequest:
    request = session.get(ReturnRequest, return_id)
    if request is None:
        raise NotFound(f"return {return_id}")
    return request


def returned_quantity(session: Session, order_line_id: int) -> int:
    return session.scalar(
        select(func.coalesce(func.sum(ReturnLine.quantity), 0))
        .join(ReturnRequest, ReturnLine.return_id == ReturnRequest.id)
        .where(ReturnLine.order_line_id == order_line_id, ReturnRequest.status.in_((REQUESTED, APPROVED)))
    )


def request_return(
    session: Session, order: Order, items, reason: str, now: datetime | None = None
) -> ReturnRequest:
    now = now or utcnow()
    if order.status != DELIVERED:
        raise ReturnError("only delivered orders can be returned")
    if order.delivered_at is not None and now - order.delivered_at > RETURN_WINDOW:
        raise ReturnError("the return window has closed")

    wanted: dict[int, int] = {}
    for item in items:
        wanted[item.order_line_id] = wanted.get(item.order_line_id, 0) + item.quantity

    lines_by_id = {line.id: line for line in order.lines}
    request = ReturnRequest(order_id=order.id, reason=reason)
    refund_cents = 0
    for line_id, quantity in wanted.items():
        line = lines_by_id.get(line_id)
        if line is None:
            raise ReturnError(f"line {line_id} is not part of order {order.id}")
        remaining = line.quantity - returned_quantity(session, line.id)
        if quantity > remaining:
            raise ReturnError(f"line {line_id}: {remaining} left to return")
        request.lines.append(ReturnLine(order_line_id=line.id, quantity=quantity))
        refund_cents += quantity * line.unit_price_cents

    request.refund_cents = refund_cents
    session.add(request)
    session.commit()
    return request


def approve_return(session: Session, gateway: FakeGateway, return_id: int) -> ReturnRequest:
    request = get_return(session, return_id)
    if request.status == REJECTED:
        raise ReturnError("a rejected return cannot be approved")

    payment = request.order.payment
    outstanding = payment.captured_cents - payment.refunded_cents
    amount = min(request.refund_cents, outstanding)
    if amount > 0:
        ref = gateway.refund(payment.provider_ref, amount)
        payment.refunded_cents = Payment.refunded_cents + amount
        session.add(Refund(payment_id=payment.id, return_id=request.id, amount_cents=amount, provider_ref=ref))

    for line in request.lines:
        stock.restock(session, line.order_line.product_id, line.quantity)

    request.status = APPROVED
    request.decided_at = utcnow()
    session.commit()
    return request


def reject_return(session: Session, return_id: int, note: str) -> ReturnRequest:
    request = get_return(session, return_id)
    if request.status != REQUESTED:
        raise ReturnError(f"return {return_id} is already {request.status}")
    request.status = REJECTED
    request.staff_note = note
    request.decided_at = utcnow()
    session.commit()
    return request
