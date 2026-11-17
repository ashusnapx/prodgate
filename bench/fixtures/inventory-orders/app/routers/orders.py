from fastapi import APIRouter, Depends, Header
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.deps import current_customer, get_gateway, get_session, require_staff
from app.models import Order
from app.schemas import CancelIn, OrderOut, PlaceOrderIn, ShipIn, WarehouseEventIn
from app.services import orders
from app.services.payments import FakeGateway

router = APIRouter(tags=["orders"])


def _owned_order(session: Session, order_id: int, customer_id: str) -> Order:
    order = session.get(Order, order_id)
    if order is None or order.customer_id != customer_id:
        raise orders.NotFound(f"order {order_id}")
    return order


@router.post("/orders", status_code=201, response_model=OrderOut)
def place_order(
    body: PlaceOrderIn,
    customer_id: str = Depends(current_customer),
    idempotency_key: str | None = Header(default=None, max_length=100),
    session: Session = Depends(get_session),
    gateway: FakeGateway = Depends(get_gateway),
):
    return orders.place_order(session, gateway, customer_id, body.items, body.card_token, idempotency_key)


@router.get("/orders", response_model=list[OrderOut])
def list_my_orders(
    status: str | None = None,
    customer_id: str = Depends(current_customer),
    session: Session = Depends(get_session),
):
    query = select(Order).where(Order.customer_id == customer_id).order_by(Order.id.desc())
    if status == "open":
        query = query.where(Order.status.in_(orders.OPEN_STATES))
    elif status:
        query = query.where(Order.status == status)
    return session.scalars(query).all()


@router.get("/orders/{order_id}", response_model=OrderOut)
def show_order(order_id: int, customer_id: str = Depends(current_customer), session: Session = Depends(get_session)):
    return _owned_order(session, order_id, customer_id)


@router.post("/orders/{order_id}/cancel", response_model=OrderOut)
def cancel_order(
    order_id: int,
    body: CancelIn,
    customer_id: str = Depends(current_customer),
    session: Session = Depends(get_session),
    gateway: FakeGateway = Depends(get_gateway),
):
    _owned_order(session, order_id, customer_id)
    return orders.cancel_order(session, gateway, order_id, body.reason)


@router.post("/orders/{order_id}/confirm", response_model=OrderOut, dependencies=[Depends(require_staff)])
def confirm_order(order_id: int, session: Session = Depends(get_session), gateway: FakeGateway = Depends(get_gateway)):
    return orders.confirm_order(session, gateway, order_id)


@router.post("/orders/{order_id}/ship", response_model=OrderOut, dependencies=[Depends(require_staff)])
def ship_order(order_id: int, body: ShipIn, session: Session = Depends(get_session)):
    return orders.ship_order(session, order_id, body.carrier, body.tracking_number)


@router.post("/warehouse/events", response_model=OrderOut, dependencies=[Depends(require_staff)])
def warehouse_event(body: WarehouseEventIn, session: Session = Depends(get_session)):
    return orders.apply_warehouse_event(session, body.order_id, body.kind, body.carrier, body.tracking_number)
