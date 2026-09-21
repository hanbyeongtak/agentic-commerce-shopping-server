# Agentic Commerce Shopping Server

A FastAPI backend for an agentic-commerce shopping flow. It manages users, stores, products and orders in MariaDB/MySQL, proxies the Agnic product search API, and settles orders in Bitcoin through **GoBTC Pay** (seller onboarding, buyer wallets, PSBT-signed payments), recording every payment in a ledger table.

> **Status:** the GoBTC Pay integration follows the public *Bitcoin Pay* guide (Parts 1–3) and was verified against a local mock server that builds and validates real PSBTs. It has **not** been exercised against the live GoBTC Pay API yet (the `register` endpoint was returning `503` during development). GoBTC Pay is **mainnet-only**: real BTC moves. Start with small amounts.

## Table of contents
1. [Features](#features)
2. [Architecture](#architecture)
3. [Tech stack](#tech-stack)
4. [Getting started](#getting-started)
5. [Configuration](#configuration)
6. [Database](#database)
7. [Payment flow end to end](#payment-flow-end-to-end)
8. [REST API](#rest-api)
9. [Batch jobs](#batch-jobs)
10. [External APIs used](#external-apis-used)
11. [Security model](#security-model)
12. [Project layout](#project-layout)
13. [Known limitations](#known-limitations)

## Features
- **CRUD APIs** for `users`, `stores`, `products` and `purchase_orders`, plus read-only `payments`.
- **JWT login** (`/auth/login`, `/auth/me`); passwords are stored as salted scrypt hashes.
- **Product search proxy** to the Agnic autofill API with a fixed server-side token.
- **Seller onboarding** on GoBTC Pay: merchant registration, e-mail verification, BIP84 xpub generation and linking, API-key issuance.
- **Buyer wallets**: per-buyer secp256k1 key, 2-of-3 multisig wallet registration, challenge-response authentication.
- **Order payments**: fixed-rate CAD→BTC conversion, PSBT build → local verification → signing → submission, confirmation via `payment/get`.
- **Payment ledger** (`payments` table): one row per payment, two payments per order (buyer→seller and seller→supplier).
- **Background batches** (every 2 minutes) for merchant registration, buyer wallet creation and order payment.

## Architecture

```
                        ┌──────────────────────────────────────────────┐
  Client / Frontend ───▶│  FastAPI (app/)                              │
                        │  auth · users · stores · products · orders   │
                        │  payments (read-only) · merchants · /search  │
                        └───────────────┬──────────────────────────────┘
                                        │                      │
                                        ▼                      ▼
                                MariaDB / MySQL         Agnic products API
                                        ▲
                                        │
        ┌───────────────────────────────┴───────────────────────────────┐
        │ Batches (batch/, APScheduler, every 2 min, DB-lock guarded)   │
        │  merchant_register_batch  buyer_wallet_batch  payment_batch   │
        └───────────────────────────────┬───────────────────────────────┘
                                        ▼
                             GoBTC Pay public API (v1.2)
```

The API server and each batch are separate processes that share the same database and code (`app/payments/`).

## Tech stack
Python 3.14 · FastAPI + Uvicorn · PyMySQL · httpx · APScheduler · PyJWT · `cryptography` (Fernet) · `embit` (BIP39/BIP32/PSBT) · MariaDB/MySQL.

## Getting started

### Prerequisites
- Python 3.10+ (developed and tested on 3.14)
- MariaDB/MySQL with a schema named `agnic`

### Install and run
```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env            # then fill in the values (see Configuration)

# API server (Swagger UI at http://localhost:8000/docs)
.venv/bin/uvicorn app.main:app --reload
# to listen on all interfaces: add --host 0.0.0.0

# Batch jobs (run each in its own process)
.venv/bin/python -m batch.merchant_register_batch
.venv/bin/python -m batch.buyer_wallet_batch
.venv/bin/python -m batch.payment_batch
# add --once to any batch to run a single cycle and exit
```

Generate the required secrets:
```bash
# ENCRYPTION_KEY (Fernet key)
.venv/bin/python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# JWT_SECRET
python3 -c "import secrets; print(secrets.token_hex(32))"
```

## Configuration
All settings are read from environment variables or `.env` ([app/config.py](app/config.py)).

| Variable | Required | Description |
|---|---|---|
| `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, `DB_NAME` | yes | Database connection (`DB_NAME` defaults to `agnic`). |
| `AGNIC_API_URL` | no | Agnic product search URL (defaults to the public endpoint). |
| `AGNIC_TOKEN` | yes for `/search` | Fixed token sent as `X-Agnic-Token`. |
| `JWT_SECRET` | yes for login | HS256 signing key. Login returns 500 if empty. |
| `JWT_EXPIRE_MINUTES` | no | Access token lifetime (default `60`). |
| `GOBTCPAY_BASE_URL` | no | GoBTC Pay base URL (default `https://api.gobtcpay.com/public/api/v1.2`). |
| `GOBTCPAY_REGISTER_URL` | no | Merchant register URL used by `merchant_register_batch`. |
| `ENCRYPTION_KEY` | yes for payments | Fernet key that encrypts seller mnemonics, buyer private keys and API keys at rest. **Back it up: losing it makes those secrets unrecoverable.** |
| `BTC_CAD_RATE` | yes for payments | Fixed rate, `1 BTC = ? CAD`. If empty, no payment is attempted. |

> `.env` is git-ignored. Never commit real secrets.

## Database
Five tables: `users`, `stores`, `products`, `purchase_orders`, `payments`. The four base tables were created manually; [sql/](sql/) holds the incremental migrations, to be applied in order:

| File | Purpose |
|---|---|
| `001_add_payment_statuses.sql` | Early payment statuses (superseded by 003). |
| `002_payment_columns.sql` | Merchant/wallet columns on `users`; `buyer_email`, `payment_id`, `payment_tx_id`, `amount_sats` on `purchase_orders`. |
| `003_customer_supplier_statuses.sql` | Replaces the order status enum with `CUSTOMER_PAYMENT_*` / `SUPPLIER_PAYMENT_*` (migrates existing rows safely). |
| `004_store_auto_update.sql` | Store auto-update flag and interval (1, 7 or 30 days). |
| `005_payments.sql` | The `payments` ledger table. |
| `006_payments_one_per_type.sql` | At most one payment per type per order. |
| `007_products_merchant_email.sql` | `products.merchant_email` (the supplier's e-mail). |

### Order status (`purchase_orders.delivery_status`)
`PENDING`, `PROCESSING`, `SHIPPED`, `DELIVERED`, `CANCELLED`, `CUSTOMER_PAYMENT_PENDING` (default for new orders), `CUSTOMER_PAYMENT_COMPLETED`, `CUSTOMER_PAYMENT_CANCELLED`, `SUPPLIER_PAYMENT_PENDING`, `SUPPLIER_PAYMENT_PROCESSING`, `SUPPLIER_PAYMENT_COMPLETED`.

### Payment ledger (`payments`)
Every order has **two payments**, at most one of each type:

| `payment_type` | Direction | `external_id` (idempotency key) |
|---|---|---|
| `CUSTOMER_PAYMENT` | buyer → seller | `order-{id}-customer` |
| `SUPPLIER_PAYMENT` | seller → supplier | `order-{id}-supplier` |

Statuses: `PENDING`, `PROCESSING`, `COMPLETED`, `FAILED`, `CANCELLED`. Each row stores the payer/payee e-mails, from/to addresses, `amount_sats`, `fee_sats`, the fiat amount and the exchange rate used, the provider ids (`provider_payment_id`, `tx_id`), the latest failure reason and timestamps. Rows survive order deletion (`order_id` becomes `NULL`) because this is a financial record.

## Payment flow end to end

1. **Sign-up** — `POST /users` only stores the user. No wallet is created yet.
2. **Merchant registration** — `merchant_register_batch` registers users without a `user_id` on GoBTC Pay (`merchant/auth/register`) and saves the returned `userId`. GoBTC Pay e-mails a 6-digit code (valid 30 minutes).
3. **Seller activation** — submit the code to `POST /merchants/{email}/verify-email`. The server verifies the e-mail, generates a BIP39 mnemonic and its BIP84 xpub (`m/84'/0'/0'`), links the xpub, and creates a secret API key. The mnemonic and key are stored encrypted. The code is single-use and the token lives 10 minutes, so this runs as one atomic sequence.
4. **Buyer wallet** — `buyer_wallet_batch` generates a secp256k1 key for each `BUYER`, stores it encrypted, registers the wallet on GoBTC Pay, and saves the multisig `wallet_address` (visible via `GET /users/{email}`). **The buyer must deposit BTC to this address** before any payment can succeed.
5. **Purchase** — creating an order (`POST /orders` with `buyer_email`) puts it in `CUSTOMER_PAYMENT_PENDING`. There is no separate "buy" endpoint; the batch picks the order up within ~2 minutes.
6. **Payment** — `payment_batch` processes each pending order:
   1. Convert `price_minor × quantity` (CAD cents) to sats with `BTC_CAD_RATE`, rounding up. Minimum 546 sats (dust limit).
   2. `merchant/payment/create` with the seller's API key and idempotency key `order-{id}-customer`; verify the returned `amountSats`.
   3. Authenticate the buyer (`get-data-to-sign` → sign challenge → `get-jwt`).
   4. `instant/psbt/build-transaction-to-sign-payment`.
   5. **Verify the PSBT before signing**: exactly one output pays the seller's address the exact amount, every other output returns to the buyer's own wallet, and the fee is at most 10,000 sats. Otherwise nothing is signed.
   6. Sign every input locally (SIGHASH_ALL, not finalized) and submit via `instant/transaction/pay-and-sign-pre-authorized-transaction`.
   7. Confirm `status == "paid"` with `merchant/payment/get`, then set the order to `CUSTOMER_PAYMENT_COMPLETED`.
7. **Supplier payment record** — once the customer payment is confirmed, a `SUPPLIER_PAYMENT` row (`PENDING`) is created with `payee_email = products.merchant_email` and the same converted amount. **Actual payout to the supplier is not implemented yet.**

Safety properties: every step persists progress (`payment_id`, `payment_tx_id`) before the next one, so a crash or retry resumes instead of paying twice; a batch-wide DB lock prevents concurrent runs; failures leave the order pending and are retried on the next cycle.

## REST API
Interactive docs: `/docs` (Swagger) and `/openapi.json`. List endpoints accept `limit` (1–500, default 50) and `offset`.

| Area | Endpoints | Notes |
|---|---|---|
| Auth | `POST /auth/login`, `GET /auth/me` | Returns a bearer JWT; `/auth/me` requires it. |
| Users | `GET/POST /users`, `GET/PATCH/DELETE /users/{email}` | Filter `user_type`. Responses never include passwords, keys, mnemonics or API secrets. |
| Stores | `GET/POST /stores`, `GET/PATCH/DELETE /stores/{store_id}` | Filters `seller_email`, `status`. Fields include `margin_rate`, `auto_update_enabled`, `auto_update_interval_days` (1/7/30). |
| Products | `GET/POST /products`, `GET/PATCH/DELETE /products/{id}` | Filter `store_id`. Includes `store_id` and `merchant_email`. |
| Orders | `GET/POST /orders`, `GET/PATCH/DELETE /orders/{order_id}` | Filters `store_id`, `product_id`, `buyer_email`, `delivery_status`. `quantity` must be > 0. |
| Payments | `GET /payments`, `GET /payments/{id}` | Read-only ledger. Filters `order_id`, `payment_type`, `status`, `payer_email`, `payee_email`. |
| Merchants | `POST /merchants/{email}/verify-email` | Body `{"code": "123456"}`; completes seller onboarding. |
| Search | `GET /search?q=water&country=CA&limit=10` | Proxies Agnic and returns its response as is. |

Error mapping: unknown ids → `404`; duplicate keys → `409`; deleting a referenced row → `409`; reference to a missing row → `400`; validation errors → `422`; upstream payment-provider failures → `502`.

## Batch jobs
All batches share [batch/runner.py](batch/runner.py): they run once immediately, then every 2 minutes; `--once` runs a single cycle. Each takes a MySQL advisory lock (`GET_LOCK`), so running two copies is safe.

| Batch | Selects | Does |
|---|---|---|
| `merchant_register_batch` | `users.user_id IS NULL` (max 50) | Registers the user on GoBTC Pay and stores `userId`. Failures are logged and retried next cycle. |
| `buyer_wallet_batch` | `BUYER` users without `wallet_address` (max 50) | Generates and encrypts the key first, then registers the wallet and stores the deposit address. |
| `payment_batch` | `CUSTOMER_PAYMENT_PENDING` orders with a `buyer_email` (max 100) | Runs the payment flow above and marks the order `CUSTOMER_PAYMENT_COMPLETED`. Orders without `buyer_email` are ignored. |

## External APIs used

**Agnic**
- `GET /api/autofill/products/search` — product discovery (proxied by `GET /search`).

**GoBTC Pay** (`https://api.gobtcpay.com/public/api/v1.2`)

| Part | Endpoints |
|---|---|
| 1 — Seller | `POST /merchant/auth/register`, `/merchant/auth/verify-email`, `/merchant/auth/xpub/link-authorized`, `/merchant/api-key/create` |
| 2 — Buyer | `POST /instant/wallet/register`, `/instant/auth/get-data-to-sign`, `/instant/auth/get-jwt` |
| 3 — Payment | `POST /merchant/payment/create`, `/instant/psbt/build-transaction-to-sign-payment`, `/instant/transaction/pay-and-sign-pre-authorized-transaction`, `/merchant/payment/get` |

The `payment.status.updated` webhook is not used; payment status is polled with `payment/get`.

## Security model
- **Encryption at rest**: seller mnemonics, buyer private keys and merchant API secrets are encrypted with Fernet (`ENCRYPTION_KEY`) before being written to the database. The server signs on behalf of buyers, so it is a custodial design.
- **Passwords**: users' passwords are hashed with scrypt; they are never returned by any endpoint.
- **PSBT validation**: the server never signs a PSBT it has not checked (recipient, amount, change destination, fee cap).
- **Secrets hygiene**: `.env` is git-ignored; API responses expose only non-secret payment fields (e.g. `wallet_address`, `merchant_xpub`).

## Project layout
```
app/
  main.py            FastAPI app, CORS, error handlers, products and search routes
  config.py          Settings (env / .env)
  db.py, crud.py     Connection helper and small CRUD helpers
  schemas.py         Product models
  security.py        scrypt password hashing
  routers/           auth, users, stores, orders, payments, merchants
  payments/
    client.py        GoBTC Pay HTTP client
    keys.py          BIP39/BIP32 wallets, challenge signing, PSBT verify + sign
    service.py       Seller onboarding, buyer wallets, order payment
    ledger.py        payments-table recording
    crypto.py        Fernet encrypt/decrypt
    errors.py        PaymentError
batch/
  runner.py                   Shared scheduler (--once support)
  merchant_register_batch.py  buyer_wallet_batch.py  payment_batch.py
sql/                          Ordered schema migrations (001–007)
```

## Known limitations
- **Not verified live**: the GoBTC Pay integration has only been tested against a mock server. The response envelope (`result.$case`) is handled defensively, but exact live shapes are unconfirmed.
- **Supplier payout**: only the ledger row is created; nothing is actually paid to suppliers yet. Supplier amount currently equals the customer amount (product price × quantity); `margin_rate` is not applied.
- **No token refresh / resend**: the guide documents no merchant token refresh or code-resend endpoint, so a failed onboarding after the single-use code may require a fresh code from GoBTC Pay.
- **Strict PSBT check**: an unexpected extra output in a live PSBT (e.g. a platform fee output) would make the server refuse to sign.
- **No API authorization**: apart from `/auth/me`, endpoints (including `DELETE /users/{email}`) are unauthenticated.
- **CORS** currently allows all origins in [app/main.py](app/main.py); the `CORS_ORIGINS` setting exists but is not used.
- **Merchant registration password** is a fixed value in `batch/merchant_register_batch.py` and is shared by all merchants — replace it before any real use.
- **Unused columns**: `users.access_token`, `refresh_token`, `expire_at` and `purchase_orders.prefix`, `secret`, `type` are not used by the code. Store auto-update settings are stored but no job acts on them.
- **Retries**: a payment that keeps failing (e.g. an unfunded buyer wallet) is retried every 2 minutes indefinitely; there is no retry cap or terminal `FAILED` transition yet.
- **Confirmation delay**: GoBTC Pay reports `paid` within seconds, but on-chain confirmation (`paidAt`) can take hours.
