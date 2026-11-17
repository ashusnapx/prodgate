# billing

Subscription billing for merchants: plans, subscriptions with trials, invoices paid through a card provider, provider webhooks, refunds and plan changes with proration. Built with FastAPI and SQLAlchemy on SQLite.

## Accounts

Every route except the webhook and the cron job takes `X-Account-Id`, the merchant. A merchant sees and changes only its own plans, subscriptions and invoices, and its subscriptions can only be on its own plans. Customers are the merchant's own references (`customer_ref`).

## Subscriptions

- `POST /plans {code, name, price_cents, interval_days, trial_days}` defines a plan.
- `POST /subscriptions {customer_ref, plan_code}` starts a subscription: `trialing` until the trial ends if the plan has one, otherwise `active` with its first period invoiced and charged straight away.
- Status moves `trialing` → `active` → `past_due` (a payment failed) → `active` again once the invoice is paid. `canceled` is final: nothing brings a canceled subscription back. A payment that settles after cancellation stays on its invoice (refund it if needed) but does not restart the subscription.
- `POST /subscriptions/{id}/cancel {at_period_end}`: with `true` (the default) the subscription runs to the end of the current period, or of the trial, and then cancels without another charge. With `false` it cancels now and voids its unpaid invoices.
- `POST /subscriptions/{id}/change-plan {plan_code, request_id}` switches plan now. An upgrade on an active subscription is charged the price difference for the rest of the period, as a proration invoice; downgrades and trial changes cost nothing. Repeating a `request_id` returns the first result instead of changing or charging again.

## Invoices and payments

- Invoice status: `open` → `pending` (charge sent) → `paid` or `failed`; or `void`. `POST /invoices/{id}/pay` charges an open or failed invoice (the dashboard's Pay button). A paid invoice stays paid.
- The provider answers a charge with `succeeded`, `failed` or `processing`. It also sends `payment.succeeded` or `payment.failed` to `POST /webhooks/provider` for every charge, including ones whose response already said `succeeded`. Webhooks are signed (`X-Signature: sha256=<HMAC of the body>`), retried until acknowledged and may arrive out of order. An invoice's paid amount is the sum of its charges.
- `POST /invoices/{id}/refunds {amount_cents}` with an `Idempotency-Key` header refunds up to what was paid and not yet refunded. Repeating a key returns the first refund and never refunds twice.

## Billing run

`POST /jobs/billing-cycle` (cron every 15 minutes, `X-Cron-Token`) ends trials that are over, renews active subscriptions whose period ended (or cancels those set to cancel at period end), charges open invoices, and asks the provider about invoices that have been pending for over an hour, so that no invoice stays pending when a webhook is lost. Two overlapping runs never bill the same period twice.

`app/provider.py` holds the provider interface and the in-memory provider used locally and in tests.

Errors come back as Problem Details JSON (`404`, `409` wrong state, `502` provider unreachable).

## Running

```
./run_tests.sh
```
