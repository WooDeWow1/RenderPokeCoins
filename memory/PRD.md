# PokéForge — PRD

## Original problem statement
Full-stack e-commerce web app (React + FastAPI + MongoDB) for selling Pokémon GO digital items and services.
Categories: Pokécoin Bundles, Event Passes, Shundo Hunting Services (Coming Soon — private simulation tool suite).
Cart rule: an Event Pass cannot be added or purchased without a Pokécoin Bundle in the cart.
Checkout collects PTC (Pokémon Trainer Club) username + password, encrypted at rest.
Order statuses Pending / Processing (Logged In) / Completed, per-order chat, alerts on Processing & Completed.
Admin dashboard for product CRUD, order management, status updates and decrypting PTC credentials.
UI: premium dark-mode hacker-forum gaming aesthetic with Snorlax / Gengar / Psyduck imagery, mobile responsive.

## User choices / decisions
- JWT email/password auth (Bearer tokens), seeded admin `officialwifi@icloud.com` / `admin`
- Guest checkout: cart, /checkout, /dashboard and order tracking are PUBLIC; only /admin is gated
- Payments: **SellAuth** (crypto + Cash App). Stripe was removed entirely (sandbox deleted, package uninstalled)
- Notifications: in-app for registered users + transactional email of the tracking link on payment

## Architecture
- Backend `/app/backend`: `server.py` (routes), `security.py` (bcrypt, JWT, Fernet), `models.py` (Pydantic + PyObjectId), `sellauth.py` (SellAuth REST client), `emailer.py` (managed email + phishing-safety gate).
- Auth: `Authorization: Bearer` JWT (localStorage `pokeforge_token`). Cookies unused — the preview proxy rewrites CORS ACAO to `*`.
- Anti-spam payment flow: checkout writes ONLY to `checkout_sessions` (TTL index on `expires_at`, 30 min auto-delete) with Fernet-encrypted PTC creds → SellAuth invoice created with `custom_fields.checkout_session_id` → user redirected to SellAuth → signed webhook `POST /api/webhooks/sellauth` verifies HMAC-SHA256 of the raw body, re-checks invoice status via the SellAuth API, then promotes the session into a permanent `orders` doc, sends the in-app notification and emails the `/order/{id}` tracking link. Idempotent via `webhook_events` unique index (inserted after successful promotion).
- Collections: users, products, orders, messages, notifications, checkout_sessions (TTL), webhook_events, login_attempts.
- Frontend: React Router, Tailwind, shadcn, framer-motion, sonner. Unbounded + JetBrains Mono, `#050505` void black with `#00ffcc` neon.

## User personas
- Trainer (customer or guest): buys coins/passes, tracks orders via emailed link, chats with the operator.
- Operator (admin): manages the catalog weekly, fulfils orders, reveals PTC credentials, updates statuses.

## Implemented
- 2026-06: JWT auth + seeded admin, brute-force lockout, admin-gated routes; storefront with neon Snorlax/Gengar/Psyduck art; cart with dual-sided Event Pass ↔ Pokécoin Bundle validation; PTC checkout with Fernet encryption; customer dashboard, order detail with status timeline + stay-logged-out warning; per-order chat; in-app notification bell; admin console (orders, statuses, PTC reveal, product CRUD); mobile responsive
- 2026-06: guest checkout (public cart/checkout/order tracking), admin credentials changed, Shundo section copy + second Shundo product
- 2026-06: Stripe removed; SellAuth + temporary `checkout_sessions` (30 min TTL) + signed webhook order promotion + tracking-link email; `/order/{id}` tracking route

## Known blockers
- SellAuth's Checkout API is not enabled on the store's current subscription plan → `POST /api/orders/checkout` returns 503 with a clear message. Paid path verified via signed webhook simulation (`/app/scripts/simulate_sellauth_webhook.py`).

## Backlog
- P1: verify live SellAuth invoice creation once the plan is upgraded; capture the real webhook payload shape and tighten field mapping
- P1: guest order lookup by email + order number; credential auto-purge after completion
- P2: coupon codes, admin order search/filters, sales analytics, audit log of credential reveals
- P2: split `server.py` into routers, admin 2FA
