from sqlalchemy import update
from sqlalchemy.orm import Session

from app.models import Order, Product, Reservation


class OutOfStock(Exception):
    def __init__(self, sku: str, requested: int, available: int) -> None:
        super().__init__(f"{sku}: requested {requested}, only {available} available")
        self.sku = sku
        self.requested = requested
        self.available = available


def available(product: Product) -> int:
    return product.on_hand - product.reserved


def reserve(session: Session, order: Order) -> list[Reservation]:
    held = []
    for line in order.lines:
        product = line.product
        free = available(product)
        if free < line.quantity:
            raise OutOfStock(product.sku, line.quantity, free)
        product.reserved = product.reserved + line.quantity
        reservation = Reservation(order=order, product_id=product.id, quantity=line.quantity)
        session.add(reservation)
        held.append(reservation)
    session.flush()
    return held


def release(session: Session, reservation: Reservation) -> bool:
    released = session.execute(
        update(Reservation)
        .where(Reservation.id == reservation.id, Reservation.status == "held")
        .values(status="released")
    )
    if released.rowcount != 1:
        return False
    session.execute(
        update(Product)
        .where(Product.id == reservation.product_id)
        .values(reserved=Product.reserved - reservation.quantity)
    )
    return True


def consume(session: Session, reservation: Reservation) -> bool:
    consumed = session.execute(
        update(Reservation)
        .where(Reservation.id == reservation.id, Reservation.status == "held")
        .values(status="consumed")
    )
    if consumed.rowcount != 1:
        return False
    session.execute(
        update(Product)
        .where(Product.id == reservation.product_id)
        .values(
            reserved=Product.reserved - reservation.quantity,
            on_hand=Product.on_hand - reservation.quantity,
        )
    )
    return True


def restock(session: Session, product_id: int, quantity: int) -> None:
    session.execute(update(Product).where(Product.id == product_id).values(on_hand=Product.on_hand + quantity))
