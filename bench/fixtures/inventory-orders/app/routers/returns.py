from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.deps import current_customer, get_gateway, get_session, require_staff
from app.schemas import RejectIn, ReturnIn, ReturnOut
from app.services import orders, returns
from app.services.payments import FakeGateway

router = APIRouter(tags=["returns"])


@router.post("/orders/{order_id}/returns", status_code=201, response_model=ReturnOut)
def request_return(
    order_id: int,
    body: ReturnIn,
    customer_id: str = Depends(current_customer),
    session: Session = Depends(get_session),
):
    order = orders.get_order(session, order_id)
    return returns.request_return(session, order, body.items, body.reason)


@router.get("/returns/{return_id}", response_model=ReturnOut)
def show_return(return_id: int, customer_id: str = Depends(current_customer), session: Session = Depends(get_session)):
    request = returns.get_return(session, return_id)
    if request.order.customer_id != customer_id:
        raise orders.NotFound(f"return {return_id}")
    return request


@router.post("/returns/{return_id}/approve", response_model=ReturnOut, dependencies=[Depends(require_staff)])
def approve_return(return_id: int, session: Session = Depends(get_session), gateway: FakeGateway = Depends(get_gateway)):
    return returns.approve_return(session, gateway, return_id)


@router.post("/returns/{return_id}/reject", response_model=ReturnOut, dependencies=[Depends(require_staff)])
def reject_return(return_id: int, body: RejectIn, session: Session = Depends(get_session)):
    return returns.reject_return(session, return_id, body.note)
