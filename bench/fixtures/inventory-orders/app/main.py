from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.db import build_sessionmaker
from app.routers import orders as orders_router
from app.routers import products as products_router
from app.routers import returns as returns_router
from app.services.orders import NotFound, OrderError
from app.services.payments import FakeGateway, PaymentGatewayError
from app.services.returns import ReturnError
from app.services.stock import OutOfStock


def _problem(status: int, title: str, detail: str, **extra) -> JSONResponse:
    body = {"type": "about:blank", "title": title, "status": status, "detail": detail, **extra}
    return JSONResponse(body, status_code=status, media_type="application/problem+json")


def create_app(
    database_url: str = "sqlite:///./inventory.db",
    gateway: FakeGateway | None = None,
    staff_token: str = "dev-staff-token",
) -> FastAPI:
    app = FastAPI(title="Inventory and orders")
    app.state.sessionmaker = build_sessionmaker(database_url)
    app.state.gateway = gateway or FakeGateway()
    app.state.staff_token = staff_token

    app.include_router(products_router.router)
    app.include_router(orders_router.router)
    app.include_router(returns_router.router)

    @app.exception_handler(NotFound)
    async def not_found(_: Request, exc: NotFound):
        return _problem(404, "Not found", str(exc))

    @app.exception_handler(OrderError)
    async def order_conflict(_: Request, exc: OrderError):
        return _problem(409, "Order state conflict", str(exc))

    @app.exception_handler(ReturnError)
    async def return_conflict(_: Request, exc: ReturnError):
        return _problem(409, "Return not allowed", str(exc))

    @app.exception_handler(OutOfStock)
    async def out_of_stock(_: Request, exc: OutOfStock):
        return _problem(409, "Out of stock", str(exc), sku=exc.sku, available=exc.available)

    @app.exception_handler(PaymentGatewayError)
    async def gateway_error(_: Request, exc: PaymentGatewayError):
        return _problem(502, "Payment processor error", str(exc))

    return app
