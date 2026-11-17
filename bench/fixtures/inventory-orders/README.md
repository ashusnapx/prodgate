# Inventory and orders

A small order service for a web shop: products with stock, customer orders,
card payments and returns. FastAPI, SQLAlchemy 2, SQLite.

## How an order moves

1. **Place** (`POST /orders`): the customer sends items and a card token. The
   service reserves stock for every line and authorizes the card. An
   `Idempotency-Key` header makes a retried checkout return the same order.
   A declined card leaves the order in `payment_failed`.
2. **Confirm** (`POST /orders/{id}/confirm`, staff): captures the payment.
   Only confirmed orders are handed to the warehouse.
3. **Warehouse** (`POST /warehouse/events`, staff/integration): the warehouse
   reports `packing`, `shipped` (with carrier and tracking number) and
   `delivered`. Staff can also ship by hand (`POST /orders/{id}/ship`).
   Shipping turns the reservation into a real stock decrease.
4. **Cancel** (`POST /orders/{id}/cancel`, customer): allowed until the order
   ships. Releases reserved stock and voids or refunds the payment.
5. A background sweeper (`expire_unconfirmed_orders`) cancels placed orders
   that staff never confirmed within 24 hours.

## Returns

A customer can ask to return lines of a delivered order within 30 days
(`POST /orders/{id}/returns`). Staff approve (refund the lines and put them
back on the shelf) or reject it. A line cannot be returned more times than it
was bought.

## Stock numbers

Each product has `on_hand` (physically in the warehouse) and `reserved`
(promised to placed orders). `available = on_hand - reserved` is what new
orders can take.

## Auth

Customers send `X-Customer-Id`; staff and the warehouse integration send
`X-Staff-Token`. Customers only see their own orders and returns.

## Running

```
./run_tests.sh
uvicorn app.main:create_app --factory
```
