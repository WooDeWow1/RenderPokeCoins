# PokéForge — PRD

## Original problem statement
Full-stack e-commerce web app (React + FastAPI + MongoDB) for selling Pokémon GO digital items and services.
Categories: Pokécoin Bundles, Event Passes, Shundo Hunting Services (Coming Soon, powered by iTools/PGTools/RegiBot/Shungo).
Cart rule: an Event Pass cannot be added or purchased without a Pokécoin Bundle in the cart.
Checkout collects PTC (Pokémon Trainer Club) username + password, encrypted at rest.
Order statuses Pending / Processing (Logged In) / Completed, per-order chat, automated alerts on Processing & Completed.
Admin dashboard for product CRUD, order management, status updates and decrypting PTC credentials.
UI: premium dark-mode hacker-forum gaming aesthetic with Snorlax / Gengar / Psyduck imagery, fully mobile responsive.

## User choices
- JWT email/password auth, seeded admin
- Stripe checkout (claimable sandbox, test mode)
- In-app notifications only

## Architecture
- Backend: FastAPI (`/app/backend/server.py`), helpers in `security.py` (bcrypt, JWT, Fernet) and `models.py` (Pydantic + PyObjectId/BaseDocument).
- Auth: Bearer JWT in `Authorization` header (localStorage `pokeforge_token`). Cookies are also set but unused — the preview proxy rewrites `Access-Control-Allow-Origin` to `*`, which blocks credentialed requests.
- DB collections: users, products, orders, messages, notifications, payment_transactions, login_attempts.
- PTC credentials: Fernet symmetric encryption keyed from `PTC_ENCRYPTION_KEY`; only `/api/admin/orders/{id}/credentials` decrypts.
- Payments: Stripe Checkout, one Stripe Product/Price per catalog product (auto-synced on admin create/edit), Stripe-managed payments (tax handled by Stripe) with automatic-tax fallback. Webhook `/api/stripe/webhook` + status poll self-heal.
- Frontend: React Router, Tailwind, shadcn primitives, framer-motion, sonner. Unbounded + JetBrains Mono, `#050505` void black with `#00ffcc` neon.

## User personas
- Trainer (customer): buys coins/passes, tracks orders, chats with operator.
- Operator (admin): manages catalog weekly, fulfils orders, reveals PTC credentials, updates statuses.

## Implemented (2026-06)
- JWT auth + seeded admin, brute-force lockout, role-gated admin routes
- Storefront with hero (Snorlax/Gengar/Psyduck neon art), trust strip, category grids, Shundo marquee section
- Cart with client + server-side Event Pass ↔ Pokécoin Bundle validation, locked-card notice
- Terminal-style PTC checkout form → Stripe Checkout → order created, paid orders flip to Pending
- Customer dashboard (active/history), order detail with status timeline + "stay logged out" warning
- Per-order chat (customer ↔ admin) with polling
- In-app notification bell with alerts on Processing / Completed / cancelled / admin replies
- Admin console: order list, status buttons, PTC reveal, chat, full product CRUD with Stripe price sync
- Mobile responsive down to 390px

## Backlog
- P1: email notifications (Resend), order cancellation/refund from admin, PTC credential auto-purge after completion
- P1: Shundo Hunting Services real product flow + intake questionnaire
- P2: coupon codes, order search/filter in admin, sales analytics, admin audit log of credential reveals
- P2: split server.py into routers, 2FA for admin
