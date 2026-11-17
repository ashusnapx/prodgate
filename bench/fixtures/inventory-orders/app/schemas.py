from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ProductIn(BaseModel):
    sku: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=200)
    price_cents: int = Field(ge=0)
    on_hand: int = Field(default=0, ge=0)


class ProductOut(ORMModel):
    id: int
    sku: str
    name: str
    price_cents: int
    on_hand: int
    reserved: int

    @computed_field
    @property
    def available(self) -> int:
        return self.on_hand - self.reserved


class OrderItemIn(BaseModel):
    product_id: int
    quantity: int = Field(gt=0, le=100)


class PlaceOrderIn(BaseModel):
    items: list[OrderItemIn] = Field(min_length=1, max_length=50)
    card_token: str


class OrderLineOut(ORMModel):
    id: int
    product_id: int
    quantity: int
    unit_price_cents: int


class PaymentOut(ORMModel):
    status: str
    amount_cents: int
    captured_cents: int
    refunded_cents: int
    failure_reason: str | None


class OrderOut(ORMModel):
    id: int
    customer_id: str
    status: str
    total_cents: int
    carrier: str | None
    tracking_number: str | None
    cancel_reason: str | None
    lines: list[OrderLineOut]
    payment: PaymentOut | None


class CancelIn(BaseModel):
    reason: str = Field(default="customer request", max_length=200)


class ShipIn(BaseModel):
    carrier: str = Field(min_length=1, max_length=50)
    tracking_number: str = Field(min_length=1, max_length=100)


class WarehouseEventIn(BaseModel):
    order_id: int
    kind: Literal["packing", "shipped", "delivered"]
    carrier: str | None = None
    tracking_number: str | None = None


class ReturnItemIn(BaseModel):
    order_line_id: int
    quantity: int = Field(gt=0)


class ReturnIn(BaseModel):
    items: list[ReturnItemIn] = Field(min_length=1)
    reason: str = Field(min_length=1, max_length=500)


class ReturnOut(ORMModel):
    id: int
    order_id: int
    status: str
    reason: str
    refund_cents: int
    staff_note: str | None


class RejectIn(BaseModel):
    note: str = Field(min_length=1, max_length=500)
