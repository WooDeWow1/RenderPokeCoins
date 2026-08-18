"""PokéForge backend regression suite — SellAuth + temp Checkout Sessions.

Architecture:
- POST /api/orders/checkout writes a temporary doc to `checkout_sessions` (30 min TTL)
  and calls SellAuth. The store's plan currently returns HTTP 503 (Checkout API not
  enabled) — we treat that as expected. On any SellAuth error the session doc is deleted.
- The paid path is exercised by simulating a signed SellAuth webhook, which promotes
  the session into an `orders` doc.
- No Stripe anywhere.
"""
import hashlib
import hmac
import json
import os
import time
import uuid
from datetime import timedelta
from pathlib import Path

import pytest
import requests
from bson import ObjectId
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

BASE_URL = ""
try:
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
except Exception:
    pass
BASE_URL = BASE_URL or os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
assert BASE_URL, "REACT_APP_BACKEND_URL not configured"

API = f"{BASE_URL}/api"
LOCAL_API = "http://localhost:8001/api"  # for webhook (some ingresses strip signature header)
ADMIN_EMAIL = "officialwifi@icloud.com"
ADMIN_PASSWORD = "admin"
WEBHOOK_SECRET = os.environ["SELLAUTH_WEBHOOK_SECRET"]
TTL_MIN = int(os.environ.get("CHECKOUT_SESSION_TTL_MINUTES", "30"))

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")
mongo = MongoClient(MONGO_URL)
db = mongo[DB_NAME]


def auth(token):
    return {"Authorization": f"Bearer {token}"}


# ---------------- Fixtures ----------------
@pytest.fixture(scope="session")
def admin_token():
    r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, f"Admin login failed: {r.status_code} {r.text}"
    data = r.json()
    assert data["user"]["role"] == "admin"
    return data["access_token"]


@pytest.fixture(scope="session")
def customer():
    email = f"trainer_{uuid.uuid4().hex[:8]}@example.com"
    password = "Trainer#2026"
    r = requests.post(f"{API}/auth/register", json={"email": email, "password": password, "name": "Trainer Test"})
    assert r.status_code == 200, r.text
    data = r.json()
    return {"email": email, "password": password, "token": data["access_token"], "id": data["user"]["id"]}


@pytest.fixture(scope="session")
def customer2():
    email = f"trainer2_{uuid.uuid4().hex[:8]}@example.com"
    r = requests.post(f"{API}/auth/register", json={"email": email, "password": "Trainer#2026", "name": "T2"})
    assert r.status_code == 200
    data = r.json()
    return {"email": email, "token": data["access_token"], "id": data["user"]["id"]}


def _products():
    return requests.get(f"{API}/products").json()


def _find(category):
    for p in _products():
        if p["category"] == category and not p.get("coming_soon"):
            return p
    return None


def _make_session(email="delivered@resend.dev", user_id="", invoice_id=None):
    """Insert a checkout_sessions doc directly (mirrors what checkout() writes)."""
    bundle = _find("pokecoin_bundle")
    now = __import__("datetime").datetime.utcnow()
    doc = {
        "items": [{"product_id": bundle["id"], "name": bundle["name"], "category": bundle["category"],
                   "price": bundle["price"], "quantity": 1}],
        "total": bundle["price"],
        "user_id": user_id,
        "email": email,
        "origin_url": BASE_URL,
        "ptc_username_enc": "gAAAAABtest_ciphertext_user",  # sentinel
        "ptc_password_enc": "gAAAAABtest_ciphertext_pass",
        "status": "awaiting_payment",
        "created_at": now,
        "expires_at": now + timedelta(minutes=TTL_MIN),
    }
    if invoice_id:
        doc["invoice_id"] = invoice_id
    result = db.checkout_sessions.insert_one(doc)
    return str(result.inserted_id)


def _sign(raw: bytes) -> str:
    return hmac.new(WEBHOOK_SECRET.encode(), raw, hashlib.sha256).hexdigest()


# ---------------- No Stripe leftovers ----------------
class TestNoStripe:
    def test_stripe_routes_gone(self):
        # Legacy Stripe endpoints must 404 now
        r1 = requests.post(f"{API}/stripe/webhook", json={})
        r2 = requests.get(f"{API}/payments/status/dummyid")
        assert r1.status_code == 404, r1.status_code
        assert r2.status_code == 404, r2.status_code

    def test_no_stripe_in_source(self):
        found = []
        for root, _dirs, files in os.walk("/app/backend"):
            if any(skip in root for skip in ("__pycache__", "tests")):
                continue
            for name in files:
                if name.endswith((".py", ".txt", ".env")):
                    path = os.path.join(root, name)
                    with open(path, "r", errors="ignore") as f:
                        if "stripe" in f.read().lower():
                            found.append(path)
        assert not found, f"Stripe references left in: {found}"


# ---------------- Auth / Products ----------------
class TestAuth:
    def test_root(self):
        assert requests.get(f"{API}/").status_code == 200

    def test_me_returns_user(self, customer):
        r = requests.get(f"{API}/auth/me", headers=auth(customer["token"]))
        assert r.status_code == 200 and r.json()["email"] == customer["email"]


class TestProducts:
    def test_list_products_no_stripe_price(self):
        products = _products()
        assert len(products) >= 6
        for p in products:
            assert "_id" not in p and "id" in p
            assert "stripe_price_id" not in p

    def test_admin_crud(self, admin_token):
        payload = {"name": "TEST_Prod", "description": "d", "category": "pokecoin_bundle",
                   "price": 1.99, "coins": 100}
        r = requests.post(f"{API}/products", headers=auth(admin_token), json=payload)
        assert r.status_code == 200, r.text
        pid = r.json()["id"]
        # storefront lists it
        assert any(p["id"] == pid for p in _products())
        payload["name"] = "TEST_Prod_upd"
        r2 = requests.put(f"{API}/products/{pid}", headers=auth(admin_token), json=payload)
        assert r2.status_code == 200 and r2.json()["name"] == "TEST_Prod_upd"
        assert requests.delete(f"{API}/products/{pid}", headers=auth(admin_token)).status_code == 200


# ---------------- TTL index ----------------
class TestTTLIndex:
    def test_expires_at_ttl_index(self):
        idx = db.checkout_sessions.index_information()
        ttl = [v for v in idx.values() if v.get("expireAfterSeconds") == 0
               and v.get("key") == [("expires_at", 1)]]
        assert ttl, f"expected TTL index on expires_at with expireAfterSeconds=0; got {idx}"

    def test_webhook_events_unique_index(self):
        idx = db.webhook_events.index_information()
        assert any(v.get("unique") and v.get("key") == [("event_key", 1)] for v in idx.values())


# ---------------- Checkout: validation before session/invoice ----------------
class TestCheckoutValidation:
    def test_guest_missing_email_400(self):
        bundle = _find("pokecoin_bundle")
        before = db.checkout_sessions.count_documents({})
        orders_before = db.orders.count_documents({})
        r = requests.post(f"{API}/orders/checkout", json={
            "items": [{"product_id": bundle["id"], "quantity": 1}],
            "ptc_username": "u", "ptc_password": "p", "origin_url": BASE_URL,
        })
        assert r.status_code == 400
        assert "email" in r.json()["detail"].lower()
        assert db.checkout_sessions.count_documents({}) == before
        assert db.orders.count_documents({}) == orders_before

    def test_guest_event_pass_only_400_no_session_no_order(self):
        p = _find("event_pass")
        before_s = db.checkout_sessions.count_documents({})
        before_o = db.orders.count_documents({})
        r = requests.post(f"{API}/orders/checkout", json={
            "items": [{"product_id": p["id"], "quantity": 1}],
            "ptc_username": "u", "ptc_password": "p", "origin_url": BASE_URL,
            "email": "guest@example.com",
        })
        assert r.status_code == 400
        assert "Pok" in r.json()["detail"]
        assert db.checkout_sessions.count_documents({}) == before_s
        assert db.orders.count_documents({}) == before_o

    def test_registered_event_pass_only_400(self, customer):
        p = _find("event_pass")
        r = requests.post(f"{API}/orders/checkout", headers=auth(customer["token"]), json={
            "items": [{"product_id": p["id"], "quantity": 1}],
            "ptc_username": "u", "ptc_password": "p", "origin_url": BASE_URL,
        })
        assert r.status_code == 400


# ---------------- Checkout: SellAuth plan gate → 503, cleanup ----------------
class TestCheckoutPlanGate:
    def test_guest_checkout_503_and_no_order_no_orphan(self):
        bundle = _find("pokecoin_bundle")
        orders_before = db.orders.count_documents({})
        sess_before = db.checkout_sessions.count_documents({})
        r = requests.post(f"{API}/orders/checkout", json={
            "items": [{"product_id": bundle["id"], "quantity": 1}],
            "ptc_username": "u", "ptc_password": "p", "origin_url": BASE_URL,
            "email": "delivered@resend.dev",
        })
        # Expected behaviour: SellAuth plan gate returns 503
        assert r.status_code == 503, f"expected 503 (plan gate), got {r.status_code}: {r.text}"
        detail = r.json()["detail"].lower()
        assert "checkout api" in detail or "subscription" in detail
        # No order was created
        assert db.orders.count_documents({}) == orders_before
        # And no orphan session left behind (cleanup path deleted it)
        assert db.checkout_sessions.count_documents({}) == sess_before

    def test_registered_checkout_503_and_no_order(self, customer):
        bundle = _find("pokecoin_bundle")
        orders_before = db.orders.count_documents({})
        sess_before = db.checkout_sessions.count_documents({})
        r = requests.post(f"{API}/orders/checkout", headers=auth(customer["token"]), json={
            "items": [{"product_id": bundle["id"], "quantity": 1}],
            "ptc_username": "u", "ptc_password": "p", "origin_url": BASE_URL,
        })
        # 503 = plan gate, 502 = other SellAuth rejection (e.g. SellAuth's own email validator
        # rejecting the *@example.com sandbox address before the plan-gate error surfaces).
        # Either way the session must be cleaned up and no order created.
        assert r.status_code in (502, 503), f"got {r.status_code}: {r.text}"
        assert db.orders.count_documents({}) == orders_before
        assert db.checkout_sessions.count_documents({}) == sess_before


# ---------------- Webhook security + paid promotion ----------------
class TestWebhook:
    def test_webhook_bad_signature_401(self):
        raw = json.dumps({"invoice": {"id": "x", "status": "completed"}}).encode()
        r = requests.post(f"{LOCAL_API}/webhooks/sellauth", data=raw,
                          headers={"signature": "0" * 64, "content-type": "application/json"})
        assert r.status_code == 401

    def test_webhook_missing_signature_401(self):
        raw = json.dumps({"invoice": {"id": "x", "status": "completed"}}).encode()
        r = requests.post(f"{LOCAL_API}/webhooks/sellauth", data=raw,
                          headers={"content-type": "application/json"})
        assert r.status_code == 401

    def test_webhook_unknown_session_matched_false(self):
        raw = json.dumps({"invoice": {"id": f"unknown-{uuid.uuid4().hex[:6]}",
                                       "status": "completed",
                                       "custom_fields": {"checkout_session_id": "000000000000000000000000"}}}).encode()
        r = requests.post(f"{LOCAL_API}/webhooks/sellauth", data=raw,
                          headers={"signature": _sign(raw), "content-type": "application/json"})
        assert r.status_code == 200
        body = r.json()
        assert body.get("matched") is False

    def test_webhook_unpaid_status_creates_no_order(self):
        sid = _make_session(email="delivered@resend.dev")
        orders_before = db.orders.count_documents({})
        raw = json.dumps({"invoice": {"id": f"inv-{uuid.uuid4().hex[:6]}",
                                       "status": "pending",
                                       "custom_fields": {"checkout_session_id": sid}}}).encode()
        r = requests.post(f"{LOCAL_API}/webhooks/sellauth", data=raw,
                          headers={"signature": _sign(raw), "content-type": "application/json"})
        assert r.status_code == 200
        assert r.json().get("paid") is False
        assert db.orders.count_documents({}) == orders_before
        # session should still be awaiting_payment
        sess = db.checkout_sessions.find_one({"_id": ObjectId(sid)})
        assert sess and sess["status"] == "awaiting_payment"
        db.checkout_sessions.delete_one({"_id": ObjectId(sid)})

    def test_webhook_paid_promotes_session_to_order_and_idempotent(self, admin_token):
        sid = _make_session(email="delivered@resend.dev")
        invoice_id = f"inv-{uuid.uuid4().hex[:8]}"
        raw = json.dumps({"invoice": {"id": invoice_id, "status": "completed",
                                       "custom_fields": {"checkout_session_id": sid}}}).encode()
        sig = _sign(raw)

        orders_before = db.orders.count_documents({})
        r = requests.post(f"{LOCAL_API}/webhooks/sellauth", data=raw,
                          headers={"signature": sig, "content-type": "application/json"}, timeout=60)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("paid") is True
        order_id = body.get("order_id")
        assert order_id
        # Exactly one new order
        assert db.orders.count_documents({}) == orders_before + 1
        doc = db.orders.find_one({"_id": ObjectId(order_id)})
        assert doc["status"] == "pending"
        assert doc["payment_status"] == "paid"
        assert doc["ptc_username_enc"] == "gAAAAABtest_ciphertext_user"
        assert doc["ptc_password_enc"] == "gAAAAABtest_ciphertext_pass"
        assert doc["session_id"] == sid
        # Session marked paid
        sess = db.checkout_sessions.find_one({"_id": ObjectId(sid)})
        assert sess["status"] == "paid" and sess["order_id"] == order_id

        # Replay -> duplicate:true, no new order
        r2 = requests.post(f"{LOCAL_API}/webhooks/sellauth", data=raw,
                           headers={"signature": sig, "content-type": "application/json"})
        assert r2.status_code == 200
        assert r2.json().get("duplicate") is True
        assert db.orders.count_documents({}) == orders_before + 1

        # Store order_id for downstream tests
        pytest.paid_order_id = order_id
        pytest.paid_session_id = sid

    def test_checkout_session_status_returns_order_id(self):
        sid = pytest.paid_session_id
        r = requests.get(f"{API}/checkout-sessions/{sid}")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "paid"
        assert data["order_id"] == pytest.paid_order_id


# ---------------- Public tracking route (guest order from webhook) ----------------
class TestTracking:
    def test_public_get_guest_order(self):
        oid = pytest.paid_order_id
        r = requests.get(f"{API}/orders/{oid}")
        assert r.status_code == 200
        data = r.json()
        assert data["payment_status"] == "paid"
        assert data["status"] == "pending"
        assert "ptc_password" not in data and "ptc_password_enc" not in data
        assert data["items"] and data["total"] > 0

    def test_public_get_messages(self):
        oid = pytest.paid_order_id
        assert requests.get(f"{API}/orders/{oid}/messages").status_code == 200


# ---------------- Registered-user privacy ----------------
class TestRegisteredPrivacy:
    @pytest.fixture(scope="class")
    def registered_order_id(self, customer):
        # Create a session tied to the registered user, then promote via webhook.
        sid = _make_session(email=customer["email"], user_id=customer["id"])
        invoice_id = f"inv-{uuid.uuid4().hex[:8]}"
        raw = json.dumps({"invoice": {"id": invoice_id, "status": "completed",
                                       "custom_fields": {"checkout_session_id": sid}}}).encode()
        r = requests.post(f"{LOCAL_API}/webhooks/sellauth", data=raw,
                          headers={"signature": _sign(raw), "content-type": "application/json"}, timeout=60)
        assert r.status_code == 200 and r.json().get("order_id")
        return r.json()["order_id"]

    def test_other_user_forbidden(self, registered_order_id, customer2):
        r = requests.get(f"{API}/orders/{registered_order_id}", headers=auth(customer2["token"]))
        assert r.status_code == 403

    def test_anonymous_forbidden(self, registered_order_id):
        assert requests.get(f"{API}/orders/{registered_order_id}").status_code == 403

    def test_admin_can_read(self, registered_order_id, admin_token):
        assert requests.get(f"{API}/orders/{registered_order_id}",
                            headers=auth(admin_token)).status_code == 200

    def test_customer_cannot_reveal_creds(self, registered_order_id, customer):
        assert requests.get(f"{API}/admin/orders/{registered_order_id}/credentials",
                            headers=auth(customer["token"])).status_code == 403

    def test_admin_status_transitions_notify_customer(self, registered_order_id, admin_token, customer):
        r = requests.patch(f"{API}/admin/orders/{registered_order_id}/status",
                           headers=auth(admin_token), json={"status": "processing"})
        assert r.status_code == 200 and r.json()["status"] == "processing"
        time.sleep(0.3)
        notifs = requests.get(f"{API}/notifications", headers=auth(customer["token"])).json()
        assert any("processed" in n["title"].lower() or "logged out" in n["title"].lower() for n in notifs)
        r2 = requests.patch(f"{API}/admin/orders/{registered_order_id}/status",
                            headers=auth(admin_token), json={"status": "completed"})
        assert r2.status_code == 200
        notifs = requests.get(f"{API}/notifications", headers=auth(customer["token"])).json()
        assert any("completed" in n["title"].lower() for n in notifs)


# ---------------- Admin listing / auth gates ----------------
class TestAdminProtection:
    def test_admin_orders_requires_admin(self, customer):
        assert requests.get(f"{API}/admin/orders").status_code == 401
        assert requests.get(f"{API}/admin/orders", headers=auth(customer["token"])).status_code == 403

    def test_admin_can_list_orders(self, admin_token):
        r = requests.get(f"{API}/admin/orders", headers=auth(admin_token))
        assert r.status_code == 200 and isinstance(r.json(), list)


# ---------------- Medals category + MSRP ----------------
class TestMedalsCategory:
    def test_seeded_medals_present_with_msrp(self):
        products = _products()
        medals = [p for p in products if p["category"] == "medals"]
        assert len(medals) >= 2, f"Expected >= 2 seeded medals, got {len(medals)}"
        names = {p["name"] for p in medals}
        assert "Platinum Medal — Single Badge" in names
        assert "Platinum Medal — Full Set Grind" in names
        for p in medals:
            assert p.get("msrp") is not None and p["msrp"] > p["price"]

    def test_admin_can_create_medals_product(self, admin_token):
        payload = {"name": "TEST_MedalProd", "description": "d", "category": "medals",
                   "price": 12.5, "msrp": 25.0}
        r = requests.post(f"{API}/products", headers=auth(admin_token), json=payload)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["category"] == "medals"
        assert data["msrp"] == 25.0
        pid = data["id"]
        # Cleanup
        requests.delete(f"{API}/products/{pid}", headers=auth(admin_token))

    def test_non_admin_cannot_create_medals(self, customer):
        payload = {"name": "TEST_MedalUnauth", "description": "d", "category": "medals",
                   "price": 1.0, "msrp": 2.0}
        r = requests.post(f"{API}/products", headers=auth(customer["token"]), json=payload)
        assert r.status_code == 403

    def test_invalid_category_400(self, admin_token):
        payload = {"name": "TEST_BadCat", "description": "d", "category": "junk_category",
                   "price": 1.0}
        r = requests.post(f"{API}/products", headers=auth(admin_token), json=payload)
        assert r.status_code == 400


# ---------------- Medals cart logic ----------------
class TestMedalsCartLogic:
    def test_medals_only_does_not_unlock_event_pass(self, customer):
        """Cart with medals + event_pass but no bundle => 400."""
        medal = _find("medals")
        ep = _find("event_pass")
        assert medal and ep
        r = requests.post(f"{API}/orders/checkout", headers=auth(customer["token"]), json={
            "items": [
                {"product_id": medal["id"], "quantity": 1},
                {"product_id": ep["id"], "quantity": 1},
            ],
            "ptc_username": "u", "ptc_password": "p", "origin_url": BASE_URL,
        })
        assert r.status_code == 400
        assert "Pok" in r.json()["detail"]

    def test_medals_only_passes_validation(self, customer):
        """Medals-only checkout passes cart validation; then SellAuth plan gate (503/502)."""
        medal = _find("medals")
        assert medal
        r = requests.post(f"{API}/orders/checkout", headers=auth(customer["token"]), json={
            "items": [{"product_id": medal["id"], "quantity": 1}],
            "ptc_username": "u", "ptc_password": "p", "origin_url": BASE_URL,
        })
        # Must NOT be 400 (validation passed); should be 502/503 from SellAuth plan gate
        assert r.status_code in (502, 503), f"expected plan-gate error, got {r.status_code}: {r.text}"

    def test_medals_plus_bundle_passes_validation(self, customer):
        medal = _find("medals")
        bundle = _find("pokecoin_bundle")
        r = requests.post(f"{API}/orders/checkout", headers=auth(customer["token"]), json={
            "items": [
                {"product_id": medal["id"], "quantity": 1},
                {"product_id": bundle["id"], "quantity": 1},
            ],
            "ptc_username": "u", "ptc_password": "p", "origin_url": BASE_URL,
        })
        assert r.status_code in (502, 503), r.text


# ---------------- Waitlist ----------------
class TestWaitlist:
    def test_waitlist_public_upsert(self):
        email = f"TEST_wl_{uuid.uuid4().hex[:8]}@example.com"
        payload = {"email": email, "product_id": "shundo-1"}
        r1 = requests.post(f"{API}/waitlist", json=payload)
        assert r1.status_code == 200 and r1.json().get("ok") is True
        # Duplicate submission does not increase count (upsert)
        r2 = requests.post(f"{API}/waitlist", json=payload)
        assert r2.status_code == 200
        count = db.waitlist.count_documents({"email": email.lower(), "product_id": "shundo-1"})
        assert count == 1
        db.waitlist.delete_many({"email": email.lower()})

    def test_admin_waitlist_requires_admin(self, customer):
        assert requests.get(f"{API}/admin/waitlist").status_code == 401
        assert requests.get(f"{API}/admin/waitlist",
                            headers=auth(customer["token"])).status_code == 403

    def test_admin_waitlist_lists(self, admin_token):
        r = requests.get(f"{API}/admin/waitlist", headers=auth(admin_token))
        assert r.status_code == 200 and isinstance(r.json(), list)
