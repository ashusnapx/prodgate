from datetime import datetime, timezone

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    sku: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    price_cents: Mapped[int]
    on_hand: Mapped[int] = mapped_column(default=0)
    reserved: Mapped[int] = mapped_column(default=0)


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (UniqueConstraint("customer_id", "idempotency_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    total_cents: Mapped[int] = mapped_column(default=0)
    idempotency_key: Mapped[str | None] = mapped_column(String(100))
    carrier: Mapped[str | None] = mapped_column(String(50))
    tracking_number: Mapped[str | None] = mapped_column(String(100))
    cancel_reason: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)
    delivered_at: Mapped[datetime | None]

    lines: Mapped[list["OrderLine"]] = relationship(back_populates="order", cascade="all, delete-orphan")
    reservations: Mapped[list["Reservation"]] = relationship(back_populates="order")
    payment: Mapped["Payment | None"] = relationship(back_populates="order")


class OrderLine(Base):
    __tablename__ = "order_lines"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"))
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    quantity: Mapped[int]
    unit_price_cents: Mapped[int]

    order: Mapped[Order] = relationship(back_populates="lines")
    product: Mapped[Product] = relationship()


class Reservation(Base):
    __tablename__ = "reservations"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"))
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    quantity: Mapped[int]
    status: Mapped[str] = mapped_column(String(16), default="held")
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    order: Mapped[Order] = relationship(back_populates="reservations")


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), unique=True)
    status: Mapped[str] = mapped_column(String(16))
    amount_cents: Mapped[int]
    captured_cents: Mapped[int] = mapped_column(default=0)
    refunded_cents: Mapped[int] = mapped_column(default=0)
    provider_ref: Mapped[str | None] = mapped_column(String(64))
    failure_reason: Mapped[str | None] = mapped_column(String(200))

    order: Mapped[Order] = relationship(back_populates="payment")


class ReturnRequest(Base):
    __tablename__ = "returns"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"))
    status: Mapped[str] = mapped_column(String(16), default="requested")
    reason: Mapped[str] = mapped_column(String(500))
    refund_cents: Mapped[int] = mapped_column(default=0)
    staff_note: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    decided_at: Mapped[datetime | None]

    order: Mapped[Order] = relationship()
    lines: Mapped[list["ReturnLine"]] = relationship(back_populates="request", cascade="all, delete-orphan")


class ReturnLine(Base):
    __tablename__ = "return_lines"

    id: Mapped[int] = mapped_column(primary_key=True)
    return_id: Mapped[int] = mapped_column(ForeignKey("returns.id"))
    order_line_id: Mapped[int] = mapped_column(ForeignKey("order_lines.id"))
    quantity: Mapped[int]

    request: Mapped[ReturnRequest] = relationship(back_populates="lines")
    order_line: Mapped[OrderLine] = relationship()


class Refund(Base):
    __tablename__ = "refunds"

    id: Mapped[int] = mapped_column(primary_key=True)
    payment_id: Mapped[int] = mapped_column(ForeignKey("payments.id"))
    return_id: Mapped[int | None] = mapped_column(ForeignKey("returns.id"))
    amount_cents: Mapped[int]
    provider_ref: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
