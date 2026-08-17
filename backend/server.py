import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

import jwt  # noqa: E402
import stripe  # noqa: E402
from bson import ObjectId  # noqa: E402
from bson.errors import InvalidId  # noqa: E402
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, Response  # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402
from starlette.middleware.cors import CORSMiddleware  # noqa: E402

from models import (  # noqa: E402
    CATEGORIES,
    ORDER_STATUSES,
    CheckoutRequest,
    LoginRequest,
    Message,
    MessageIn,
    Notification,
    Order,
    OrderItem,
    Product,
    ProductIn,
    RegisterRequest,
    StatusUpdate,
    UserPublic,
    utc_now,
)
from security import (  # noqa: E402
    create_access_token,
    create_refresh_token,
    decode_token,
    decrypt_secret,
    encrypt_secret,
    hash_password,
    verify_password,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

client = AsyncIOMotorClient(os.environ["MONGO_URL"])
db = client[os.environ["DB_NAME"]]

stripe.api_key = os.environ["STRIPE_SECRET_KEY"]
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
TAX_MODE = "full"

app = FastAPI(title="PokéForge API")
api = APIRouter(prefix="/api")


def oid(value: str) -> ObjectId:
    try:
        return ObjectId(value)
    except (InvalidId, TypeError):
        raise HTTPException(status_code=400, detail="Invalid id")


def set_auth_cookies(response: Response, user_id: str, email: str, role: str):
    response.set_cookie("access_token", create_access_token(user_id, email, role), httponly=True,
                        secure=True, samesite="none", max_age=3600, path="/")
    response.set_cookie("refresh_token", create_refresh_token(user_id), httponly=True,
                        secure=True, samesite="none", max_age=604800, path="/")


async def get_current_user(request: Request) -> dict:
    token = request.cookies.get("access_token")
    if not token:
        header = request.headers.get("Authorization", "")
        if header.startswith("Bearer "):
            token = header[7:]
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = decode_token(token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Invalid token type")
    user = await db.users.find_one({"_id": oid(payload["sub"])})
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


async def get_admin_user(user: dict = Depends(get_current_user)) -> dict:
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


def public_user(user: dict) -> dict:
    return {
        "id": str(user["_id"]),
        "email": user["email"],
        "name": user.get("name", ""),
        "role": user.get("role", "customer"),
    }


# ---------------- Auth ----------------
@api.post("/auth/register")
async def register(payload: RegisterRequest, response: Response):
    email = payload.email.lower()
    if await db.users.find_one({"email": email}):
        raise HTTPException(status_code=400, detail="Email already registered")
    doc = {
        "email": email,
        "password_hash": hash_password(payload.password),
        "name": payload.name,
        "role": "customer",
        "created_at": utc_now(),
    }
    result = await db.users.insert_one(doc)
    doc["_id"] = result.inserted_id
    set_auth_cookies(response, str(result.inserted_id), email, "customer")
    return {
        "user": public_user(doc),
        "access_token": create_access_token(str(result.inserted_id), email, "customer"),
    }


@api.post("/auth/login")
async def login(payload: LoginRequest, request: Request, response: Response):
    email = payload.email.lower()
    ip = request.client.host if request.client else "unknown"
    identifier = f"{ip}:{email}"
    attempt = await db.login_attempts.find_one({"identifier": identifier})
    if attempt and attempt.get("count", 0) >= 5:
        locked_until = attempt.get("locked_until")
        if locked_until and locked_until.replace(tzinfo=timezone.utc) > utc_now():
            raise HTTPException(status_code=429, detail="Too many failed attempts. Try again in 15 minutes.")
        await db.login_attempts.delete_one({"identifier": identifier})

    user = await db.users.find_one({"email": email})
    if not user or not verify_password(payload.password, user["password_hash"]):
        await db.login_attempts.update_one(
            {"identifier": identifier},
            {"$inc": {"count": 1}, "$set": {"locked_until": utc_now() + timedelta(minutes=15)}},
            upsert=True,
        )
        raise HTTPException(status_code=401, detail="Invalid email or password")
    await db.login_attempts.delete_one({"identifier": identifier})
    role = user.get("role", "customer")
    set_auth_cookies(response, str(user["_id"]), email, role)
    return {
        "user": public_user(user),
        "access_token": create_access_token(str(user["_id"]), email, role),
    }


@api.post("/auth/logout")
async def logout(response: Response):
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/")
    return {"ok": True}


@api.get("/auth/me")
async def me(user: dict = Depends(get_current_user)):
    return public_user(user)


@api.post("/auth/refresh")
async def refresh(request: Request, response: Response):
    token = request.cookies.get("refresh_token")
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = decode_token(token)
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid token type")
    user = await db.users.find_one({"_id": oid(payload["sub"])})
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    role = user.get("role", "customer")
    set_auth_cookies(response, str(user["_id"]), user["email"], role)
    return {
        "user": public_user(user),
        "access_token": create_access_token(str(user["_id"]), user["email"], role),
    }


# ---------------- Products ----------------
def ensure_stripe_price(product_id: str, name: str, amount: float, existing_price_id: Optional[str]) -> Optional[str]:
    try:
        lookup_key = f"pgx_{product_id}"
        unit_amount = int(round(amount * 100))
        if existing_price_id:
            try:
                price = stripe.Price.retrieve(existing_price_id)
                if price.active and price.unit_amount == unit_amount:
                    return existing_price_id
                stripe.Price.modify(existing_price_id, active=False, lookup_key=None)
            except stripe.error.StripeError:
                pass
        products = [
            p for p in stripe.Product.list(active=True, limit=100).auto_paging_iter()
            if p.to_dict().get("metadata", {}).get("emergent_product_id") == product_id
        ]
        sp = products[0] if products else stripe.Product.create(
            name=name,
            tax_code="txcd_10000000",
            metadata={"managed_by": "emergent", "emergent_product_id": product_id},
        )
        new_price = stripe.Price.create(
            product=sp.id, unit_amount=unit_amount, currency="usd",
            lookup_key=lookup_key, transfer_lookup_key=True,
        )
        return new_price.id
    except stripe.error.StripeError as exc:
        logger.warning("Stripe price sync failed: %s", exc)
        return existing_price_id


@api.get("/products")
async def list_products(include_inactive: bool = False):
    query = {} if include_inactive else {"active": True}
    docs = await db.products.find(query).sort("price", 1).to_list(500)
    return [Product.from_mongo(d).model_dump(by_alias=False) for d in docs]


@api.post("/products")
async def create_product(payload: ProductIn, admin: dict = Depends(get_admin_user)):
    if payload.category not in CATEGORIES:
        raise HTTPException(status_code=400, detail="Invalid category")
    product = Product(**payload.model_dump())
    result = await db.products.insert_one(product.to_mongo())
    pid = str(result.inserted_id)
    price_id = ensure_stripe_price(pid, payload.name, payload.price, None)
    await db.products.update_one({"_id": result.inserted_id}, {"$set": {"stripe_price_id": price_id}})
    doc = await db.products.find_one({"_id": result.inserted_id})
    return Product.from_mongo(doc).model_dump(by_alias=False)


@api.put("/products/{product_id}")
async def update_product(product_id: str, payload: ProductIn, admin: dict = Depends(get_admin_user)):
    if payload.category not in CATEGORIES:
        raise HTTPException(status_code=400, detail="Invalid category")
    existing = await db.products.find_one({"_id": oid(product_id)})
    if not existing:
        raise HTTPException(status_code=404, detail="Product not found")
    updates = payload.model_dump()
    updates["stripe_price_id"] = ensure_stripe_price(
        product_id, payload.name, payload.price, existing.get("stripe_price_id")
    )
    await db.products.update_one({"_id": oid(product_id)}, {"$set": updates})
    doc = await db.products.find_one({"_id": oid(product_id)})
    return Product.from_mongo(doc).model_dump(by_alias=False)


@api.delete("/products/{product_id}")
async def delete_product(product_id: str, admin: dict = Depends(get_admin_user)):
    result = await db.products.delete_one({"_id": oid(product_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Product not found")
    return {"ok": True}


# ---------------- Orders ----------------
def order_response(doc: dict, include_credentials: bool = False) -> dict:
    order = Order.from_mongo(doc)
    data = order.model_dump(by_alias=False)
    data.pop("ptc_username_enc", None)
    data.pop("ptc_password_enc", None)
    data["ptc_username_masked"] = "•" * 8
    if include_credentials:
        data["ptc_username"] = decrypt_secret(doc["ptc_username_enc"])
        data["ptc_password"] = decrypt_secret(doc["ptc_password_enc"])
    return data


async def notify(user_id: str, order_id: str, title: str, body: str):
    n = Notification(user_id=user_id, order_id=order_id, title=title, body=body)
    await db.notifications.insert_one(n.to_mongo())


@api.post("/orders/checkout")
async def checkout(payload: CheckoutRequest, user: dict = Depends(get_current_user)):
    if not payload.items:
        raise HTTPException(status_code=400, detail="Cart is empty")
    items: List[OrderItem] = []
    for entry in payload.items:
        doc = await db.products.find_one({"_id": oid(entry.product_id), "active": True})
        if not doc:
            raise HTTPException(status_code=400, detail="A product in your cart is unavailable")
        if doc.get("coming_soon"):
            raise HTTPException(status_code=400, detail=f"{doc['name']} is not available yet")
        items.append(OrderItem(
            product_id=str(doc["_id"]), name=doc["name"], category=doc["category"],
            price=float(doc["price"]), quantity=entry.quantity,
        ))

    has_pass = any(i.category == "event_pass" for i in items)
    has_coins = any(i.category == "pokecoin_bundle" for i in items)
    if has_pass and not has_coins:
        raise HTTPException(
            status_code=400,
            detail="An Event Pass requires at least one Pokécoin Bundle in your cart.",
        )

    total = round(sum(i.price * i.quantity for i in items), 2)
    order = Order(
        user_id=str(user["_id"]),
        user_email=user["email"],
        items=items,
        total=total,
        status="awaiting_payment",
        ptc_username_enc=encrypt_secret(payload.ptc_username),
        ptc_password_enc=encrypt_secret(payload.ptc_password),
    )
    result = await db.orders.insert_one(order.to_mongo())
    order_id = str(result.inserted_id)

    line_items = []
    for i in items:
        doc = await db.products.find_one({"_id": oid(i.product_id)})
        price_id = doc.get("stripe_price_id") or ensure_stripe_price(i.product_id, i.name, i.price, None)
        if not price_id:
            raise HTTPException(status_code=500, detail="Payment setup unavailable, try again later")
        if not doc.get("stripe_price_id"):
            await db.products.update_one({"_id": oid(i.product_id)}, {"$set": {"stripe_price_id": price_id}})
        line_items.append({"price": price_id, "quantity": i.quantity})

    kwargs = dict(
        line_items=line_items,
        mode="payment",
        success_url=f"{payload.origin_url}/payment/success?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{payload.origin_url}/payment/cancel",
        metadata={"user_id": str(user["_id"]), "order_id": order_id},
    )
    try:
        if TAX_MODE == "full":
            try:
                session = stripe.checkout.Session.create(**kwargs, managed_payments={"enabled": True})
            except stripe.error.InvalidRequestError as exc:
                msg = (exc.user_message or str(exc)).lower()
                if "managed payments" in msg or "ineligible" in msg:
                    session = stripe.checkout.Session.create(
                        **kwargs, automatic_tax={"enabled": True}, billing_address_collection="required"
                    )
                else:
                    raise
        else:
            session = stripe.checkout.Session.create(
                **kwargs, automatic_tax={"enabled": True}, billing_address_collection="required"
            )
    except stripe.error.StripeError as exc:
        await db.orders.delete_one({"_id": result.inserted_id})
        raise HTTPException(status_code=500, detail=f"Stripe error: {exc.user_message or str(exc)}")

    await db.orders.update_one({"_id": result.inserted_id}, {"$set": {"session_id": session.id}})
    await db.payment_transactions.insert_one({
        "session_id": session.id, "order_id": order_id, "user_id": str(user["_id"]),
        "amount": total, "currency": "usd", "status": "initiated", "payment_status": "pending",
        "created_at": utc_now(), "updated_at": utc_now(),
    })
    return {"checkout_url": session.url, "session_id": session.id, "order_id": order_id}


async def mark_paid(session_id: str, payment_status: str = "paid", payment_intent: Optional[str] = None):
    record = await db.payment_transactions.find_one({"session_id": session_id})
    if not record or record.get("payment_status") == "paid":
        return
    await db.payment_transactions.update_one(
        {"session_id": session_id, "payment_status": {"$ne": "paid"}},
        {"$set": {"status": "completed", "payment_status": payment_status,
                  "stripe_payment_intent_id": payment_intent, "updated_at": utc_now()}},
    )
    order = await db.orders.find_one({"session_id": session_id})
    if order and order.get("status") == "awaiting_payment":
        await db.orders.update_one(
            {"_id": order["_id"]},
            {"$set": {"status": "pending", "payment_status": "paid", "updated_at": utc_now()}},
        )
        await notify(order["user_id"], str(order["_id"]), "Order received",
                     "Payment confirmed. Your order is queued — a operator will pick it up shortly.")


@api.get("/payments/status/{session_id}")
async def payment_status(session_id: str):
    record = await db.payment_transactions.find_one({"session_id": session_id})
    if not record:
        raise HTTPException(status_code=404, detail="Transaction not found")
    if record.get("payment_status") != "paid":
        try:
            s = stripe.checkout.Session.retrieve(session_id)
            if s.payment_status == "paid" or s.status == "complete":
                await mark_paid(session_id, "paid", s.payment_intent)
                record = await db.payment_transactions.find_one({"session_id": session_id})
        except stripe.error.StripeError:
            pass
    return {"session_id": record["session_id"], "status": record["status"],
            "payment_status": record["payment_status"], "order_id": record.get("order_id")}


@app.post("/api/stripe/webhook")
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")
    try:
        event = stripe.Webhook.construct_event(payload, sig, STRIPE_WEBHOOK_SECRET)
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid signature")
    obj, event_type = event["data"]["object"], event["type"]
    if event_type in ("checkout.session.completed", "checkout.session.async_payment_succeeded"):
        await mark_paid(obj["id"], obj.get("payment_status", "paid"), obj.get("payment_intent"))
    elif event_type == "checkout.session.async_payment_failed":
        await db.payment_transactions.update_one({"session_id": obj["id"]},
            {"$set": {"status": "failed", "payment_status": "failed", "updated_at": utc_now()}})
    elif event_type == "checkout.session.expired":
        await db.payment_transactions.update_one({"session_id": obj["id"]},
            {"$set": {"status": "expired", "payment_status": "expired", "updated_at": utc_now()}})
    return {"status": "ok"}


@api.get("/orders")
async def my_orders(user: dict = Depends(get_current_user)):
    docs = await db.orders.find({"user_id": str(user["_id"])}).sort("created_at", -1).to_list(200)
    return [order_response(d) for d in docs]


@api.get("/admin/orders")
async def all_orders(status: Optional[str] = None, admin: dict = Depends(get_admin_user)):
    query = {"status": status} if status else {}
    docs = await db.orders.find(query).sort("created_at", -1).to_list(500)
    return [order_response(d) for d in docs]


@api.get("/orders/{order_id}")
async def get_order(order_id: str, user: dict = Depends(get_current_user)):
    doc = await db.orders.find_one({"_id": oid(order_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Order not found")
    is_admin = user.get("role") == "admin"
    if not is_admin and doc["user_id"] != str(user["_id"]):
        raise HTTPException(status_code=403, detail="Not your order")
    return order_response(doc)


@api.get("/admin/orders/{order_id}/credentials")
async def reveal_credentials(order_id: str, admin: dict = Depends(get_admin_user)):
    doc = await db.orders.find_one({"_id": oid(order_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Order not found")
    return {
        "ptc_username": decrypt_secret(doc["ptc_username_enc"]),
        "ptc_password": decrypt_secret(doc["ptc_password_enc"]),
    }


@api.patch("/admin/orders/{order_id}/status")
async def update_status(order_id: str, payload: StatusUpdate, admin: dict = Depends(get_admin_user)):
    if payload.status not in ORDER_STATUSES:
        raise HTTPException(status_code=400, detail="Invalid status")
    doc = await db.orders.find_one({"_id": oid(order_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Order not found")
    await db.orders.update_one({"_id": oid(order_id)},
                               {"$set": {"status": payload.status, "updated_at": utc_now()}})
    if payload.status != doc.get("status"):
        if payload.status == "processing":
            await notify(doc["user_id"], order_id, "Order is being processed — STAY LOGGED OUT",
                         "An operator is now logged into your PTC account. Please do NOT log into your "
                         "Pokémon GO account until this order is marked Completed.")
        elif payload.status == "completed":
            await notify(doc["user_id"], order_id, "Order completed",
                         "Your order is complete. You may safely log back into your Pokémon GO account. "
                         "We recommend changing your PTC password.")
        elif payload.status == "cancelled":
            await notify(doc["user_id"], order_id, "Order cancelled",
                         "Your order was cancelled. Reply in the order chat if you need help.")
    updated = await db.orders.find_one({"_id": oid(order_id)})
    return order_response(updated)


# ---------------- Messaging ----------------
async def assert_order_access(order_id: str, user: dict) -> dict:
    doc = await db.orders.find_one({"_id": oid(order_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Order not found")
    if user.get("role") != "admin" and doc["user_id"] != str(user["_id"]):
        raise HTTPException(status_code=403, detail="Not your order")
    return doc


@api.get("/orders/{order_id}/messages")
async def list_messages(order_id: str, user: dict = Depends(get_current_user)):
    await assert_order_access(order_id, user)
    docs = await db.messages.find({"order_id": order_id}).sort("created_at", 1).to_list(500)
    return [Message.from_mongo(d).model_dump(by_alias=False) for d in docs]


@api.post("/orders/{order_id}/messages")
async def post_message(order_id: str, payload: MessageIn, user: dict = Depends(get_current_user)):
    order = await assert_order_access(order_id, user)
    role = user.get("role", "customer")
    msg = Message(order_id=order_id, sender_id=str(user["_id"]), sender_name=user.get("name", "User"),
                  sender_role=role, body=payload.body)
    result = await db.messages.insert_one(msg.to_mongo())
    if role == "admin":
        await notify(order["user_id"], order_id, "New message from support",
                     payload.body[:140])
    msg.id = str(result.inserted_id)
    return msg.model_dump(by_alias=False)


# ---------------- Notifications ----------------
@api.get("/notifications")
async def list_notifications(user: dict = Depends(get_current_user)):
    docs = await db.notifications.find({"user_id": str(user["_id"])}).sort("created_at", -1).to_list(100)
    return [Notification.from_mongo(d).model_dump(by_alias=False) for d in docs]


@api.post("/notifications/read")
async def mark_notifications_read(user: dict = Depends(get_current_user)):
    await db.notifications.update_many({"user_id": str(user["_id"]), "read": False}, {"$set": {"read": True}})
    return {"ok": True}


@api.get("/")
async def root():
    return {"message": "PokéForge API online"}


app.include_router(api)

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=".*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SEED_PRODUCTS = [
    {"name": "550 Pokécoins", "description": "Instant Pokécoin top-up delivered to your account within the hour.",
     "category": "pokecoin_bundle", "price": 4.99, "coins": 550, "badge": "STARTER",
     "image_url": "https://static.prod-images.emergentagent.com/jobs/14c26eb3-0841-4dbf-8b14-87aeae68ff36/images/b5567f7be5ab8efdf0eb610e39a8c24853b614f342cc5b99c25a7c46a759343a.jpeg"},
    {"name": "1,200 Pokécoins", "description": "Mid-tier stack. Best value per coin for regular raiders.",
     "category": "pokecoin_bundle", "price": 8.99, "coins": 1200, "badge": "POPULAR",
     "image_url": "https://static.prod-images.emergentagent.com/jobs/14c26eb3-0841-4dbf-8b14-87aeae68ff36/images/b5567f7be5ab8efdf0eb610e39a8c24853b614f342cc5b99c25a7c46a759343a.jpeg"},
    {"name": "5,200 Pokécoins", "description": "Whale stack. Storage, incubators, remote passes — all covered.",
     "category": "pokecoin_bundle", "price": 29.99, "coins": 5200, "badge": "MAX",
     "image_url": "https://static.prod-images.emergentagent.com/jobs/14c26eb3-0841-4dbf-8b14-87aeae68ff36/images/3ab05ddaf8a485b60bf1084d4dba78ab7108f82619fa73b9abc772ff7bb7068c.jpeg"},
    {"name": "GO Fest Global Ticket", "description": "Full weekend access pass. Requires a Pokécoin bundle in cart.",
     "category": "event_pass", "price": 14.99, "badge": "EVENT",
     "image_url": "https://static.prod-images.emergentagent.com/jobs/14c26eb3-0841-4dbf-8b14-87aeae68ff36/images/0c5cba41f0c264d1d048fefa4e9bdbf766fc60fa86bb591d83e3f2c8fd7e96e2.jpeg"},
    {"name": "Ghost Hour Raid Pass", "description": "Gengar Mega raid weekend timed research pass.",
     "category": "event_pass", "price": 6.99, "badge": "LIMITED",
     "image_url": "https://static.prod-images.emergentagent.com/jobs/14c26eb3-0841-4dbf-8b14-87aeae68ff36/images/d51e3620405fffdaa6274f243f8be4dcb033aecf285738dfb12c097e13f28205.jpeg"},
    {"name": "Shundo Hunt — Single Target", "description": "Location-simulated shundo hunting via iTools, PGTools, RegiBot & Shungo. Launching soon.",
     "category": "shundo_service", "price": 49.99, "badge": "COMING SOON", "coming_soon": True,
     "image_url": "https://static.prod-images.emergentagent.com/jobs/14c26eb3-0841-4dbf-8b14-87aeae68ff36/images/a1cb3e2f61373eebc47314154e840108ff51e22f6b3e2445e1d251e47e96c67c.jpeg"},
    {"name": "Shundo Hunt — Community Day Background Target",
     "description": "Operators run your account in the background all Community Day, chasing the featured shiny-hundo while you go about your day. Launching soon.",
     "category": "shundo_service", "price": 79.99, "badge": "COMING SOON", "coming_soon": True,
     "image_url": "https://static.prod-images.emergentagent.com/jobs/14c26eb3-0841-4dbf-8b14-87aeae68ff36/images/d51e3620405fffdaa6274f243f8be4dcb033aecf285738dfb12c097e13f28205.jpeg"},
]


@app.on_event("startup")
async def startup():
    await db.users.create_index("email", unique=True)
    await db.login_attempts.create_index("identifier")
    await db.orders.create_index("user_id")
    await db.messages.create_index("order_id")
    await db.notifications.create_index("user_id")

    admin_email = os.environ["ADMIN_EMAIL"].lower()
    admin_password = os.environ["ADMIN_PASSWORD"]
    existing = await db.users.find_one({"email": admin_email})
    if existing is None:
        await db.users.insert_one({
            "email": admin_email, "password_hash": hash_password(admin_password),
            "name": "Forge Admin", "role": "admin", "created_at": utc_now(),
        })
    elif not verify_password(admin_password, existing["password_hash"]):
        await db.users.update_one({"email": admin_email},
                                  {"$set": {"password_hash": hash_password(admin_password), "role": "admin"}})

    if await db.products.count_documents({}) == 0:
        for entry in SEED_PRODUCTS:
            product = Product(**entry)
            result = await db.products.insert_one(product.to_mongo())
            price_id = ensure_stripe_price(str(result.inserted_id), entry["name"], entry["price"], None)
            await db.products.update_one({"_id": result.inserted_id}, {"$set": {"stripe_price_id": price_id}})


@app.on_event("shutdown")
async def shutdown():
    client.close()
