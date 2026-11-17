from collections.abc import Iterable
from datetime import datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.models import Order, OrderLine, Payment, Product, utcnow
from app.services import stock
from app.services.payments import FakeGateway, PaymentDeclined

PENDING = "pending"
PLACED = "placed"
PAYMENT_FAILED = "payment_failed"
CONFIRMED = "confirmed"
PACKING = "packing"
SHIPPED = "shipped"
DELIVERED = "delivered"
CANCELLED = "cancelled"

FINAL_STATES = (DELIVERED, CANCELLED, PAYMENT_FAILED)
OPEN_STATES = (PLACED, CONFIRMED, PACKING, SHIPPED)


class OrderError(Exception):
    """The order's current state does not allow the request."""


class NotFound(Exception):
    pass


def get_order(session: Session, order_id: int) -> Order:
    order = session.get(Order, order_id)
    if order is None:
        raise NotFound(f"order {order_id}")
    return order


def _transition(session: Session, order_id: int, allowed_from: Iterable[str], to: str, **values) -> Order:
    claimed = session.execute(
        update(Order)
        .where(Order.id == order_id, Order.status.in_(tuple(allowed_from)))
        .values(status=to, updated_at=utcnow(), **values)
    )
    order = get_order(session, order_id)
    if claimed.rowcount != 1:
        raise OrderError(f"order {order_id} is {order.status}, cannot move to {to}")
    return order


def _build_lines(session: Session, items) -> list[OrderLine]:
    lines = []
    for item in items:
        product = session.get(Product, item.product_id)
        if product is None:
            raise NotFound(f"product {item.product_id}")
        lines.append(
            OrderLine(product=product, quantity=item.quantity, unit_price_cents=product.price_cents)
        )
    return lines


def _find_by_key(session: Session, customer_id: str, key: str) -> Order | None:
    return session.scalar(select(Order).where(Order.customer_id == customer_id, Order.idempotency_key == key))


def place_order(
    session: Session,
    gateway: FakeGateway,
    customer_id: str,
    items,
    card_token: str,
    idempotency_key: str | None = None,
) -> Order:
    if idempotency_key:
        existing = _find_by_key(session, customer_id, idempotency_key)
        if existing is not None:
            return existing

    lines = _build_lines(session, items)
    order = Order(
        customer_id=customer_id,
        idempotency_key=idempotency_key,
        status=PENDING,
        lines=lines,
        total_cents=sum(line.quantity * line.unit_price_cents for line in lines),
    )
    session.add(order)
    try:
        session.flush()
    except IntegrityError:
        session.rollback()
        existing = _find_by_key(session, customer_id, idempotency_key)
        if existing is None:
            raise
        return existing

    stock.reserve(session, order)
    try:
        ref = gateway.authorize(order.total_cents, card_token)
    except PaymentDeclined as exc:
        order.status = PAYMENT_FAILED
        order.payment = Payment(status="failed", amount_cents=order.total_cents, failure_reason=str(exc))
        session.commit()
        return order

    order.payment = Payment(status="authorized", amount_cents=order.total_cents, provider_ref=ref)
    order.status = PLACED
    session.commit()
    return order


def confirm_order(session: Session, gateway: FakeGateway, order_id: int) -> Order:
    try:
        order = _transition(session, order_id, (PLACED,), CONFIRMED)
    except OrderError:
        order = get_order(session, order_id)
        if order.status == CONFIRMED:
            return order
        raise
    payment = order.payment
    gateway.capture(payment.provider_ref, payment.amount_cents)
    payment.status = "captured"
    payment.captured_cents = payment.amount_cents
    session.commit()
    return order


def cancel_order(session: Session, gateway: FakeGateway, order_id: int, reason: str) -> Order:
    order = _transition(session, order_id, OPEN_STATES, CANCELLED, cancel_reason=reason)
    for reservation in order.reservations:
        stock.release(session, reservation)
    payment = order.payment
    if payment is not None and payment.status == "authorized":
        gateway.void(payment.provider_ref)
        payment.status = "voided"
    elif payment is not None and payment.status == "captured":
        outstanding = payment.captured_cents - payment.refunded_cents
        if outstanding > 0:
            gateway.refund(payment.provider_ref, outstanding)
            payment.refunded_cents = payment.captured_cents
        payment.status = "refunded"
    session.commit()
    return order


def ship_order(session: Session, order_id: int, carrier: str, tracking_number: str) -> Order:
    order = _transition(
        session,
        order_id,
        (PLACED, CONFIRMED, PACKING),
        SHIPPED,
        carrier=carrier,
        tracking_number=tracking_number,
    )
    for reservation in order.reservations:
        stock.consume(session, reservation)
    session.commit()
    return order


def apply_warehouse_event(
    session: Session,
    order_id: int,
    kind: str,
    carrier: str | None = None,
    tracking_number: str | None = None,
) -> Order:
    if kind == "shipped":
        return ship_order(session, order_id, carrier or "unknown", tracking_number or "")
    if kind == "delivered":
        order = _transition(session, order_id, (SHIPPED,), DELIVERED, delivered_at=utcnow())
        session.commit()
        return order

    order = get_order(session, order_id)
    if order.status in (CANCELLED, PAYMENT_FAILED):
        raise OrderError(f"order {order_id} is {order.status}")
    order.status = PACKING
    order.updated_at = utcnow()
    session.commit()
    return order


def expire_unconfirmed_orders(
    make_session: sessionmaker[Session],
    gateway: FakeGateway,
    now: datetime | None = None,
    max_age: timedelta = timedelta(hours=24),
) -> int:
    cutoff = (now or utcnow()) - max_age
    with make_session() as session:
        stale_ids = session.scalars(
            select(Order.id).where(Order.status == PLACED, Order.created_at < cutoff)
        ).all()

    expired = 0
    for order_id in stale_ids:
        with make_session() as session:
            try:
                cancel_order(session, gateway, order_id, reason="not confirmed in time")
            except OrderError:
                continue
            expired += 1
    return expired
