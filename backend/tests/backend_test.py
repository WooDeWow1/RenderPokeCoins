"""PokéForge backend end-to-end regression tests (guest checkout).

Iteration 2: /api/orders/checkout is now public. Auth is only required for the
current user's /api/orders list, admin endpoints, and notifications.
"""
import os
import uuid
import time
import pytest
import requests
from pymongo import MongoClient
from bson import ObjectId
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

# Prefer frontend .env public URL to hit the same ingress users hit.
BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
try:
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
except Exception:
    pass
assert BASE_URL, "REACT_APP_BACKEND_URL not configured"

API = f"{BASE_URL}/api"
ADMIN_EMAIL = "officialwifi@icloud.com"
ADMIN_PASSWORD = "admin"

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")
mongo = MongoClient(MONGO_URL)
db = mongo[DB_NAME]


def auth(token):
    return {"Authorization": f"Bearer {token}"}


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
    password = "Trainer#2026"
    r = requests.post(f"{API}/auth/register", json={"email": email, "password": password, "name": "Trainer Two"})
    assert r.status_code == 200, r.text
    data = r.json()
    return {"email": email, "password": password, "token": data["access_token"], "id": data["user"]["id"]}


def _products():
    return requests.get(f"{API}/products").json()


def _find(category):
    for p in _products():
        if p["category"] == category and not p.get("coming_soon"):
            return p
    return None


# ---------------- Auth ----------------
class TestAuth:
    def test_root(self):
        r = requests.get(f"{API}/")
        assert r.status_code == 200

    def test_me_requires_auth(self):
        r = requests.get(f"{API}/auth/me")
        assert r.status_code == 401

    def test_me_returns_user(self, customer):
        r = requests.get(f"{API}/auth/me", headers=auth(customer["token"]))
        assert r.status_code == 200
        assert r.json()["email"] == customer["email"]
        assert r.json()["role"] == "customer"

    def test_admin_login(self, admin_token):
        assert admin_token


# ---------------- Products ----------------
class TestProducts:
    def test_list_products(self):
        products = _products()
        assert len(products) >= 6
        cats = {p["category"] for p in products}
        assert {"pokecoin_bundle", "event_pass", "shundo_service"}.issubset(cats)
        for p in products:
            assert "_id" not in p and "id" in p

    def test_product_writes_require_admin(self, customer):
        # anonymous
        r = requests.post(f"{API}/products", json={"name": "x", "description": "x",
                                                   "category": "pokecoin_bundle", "price": 1.0})
        assert r.status_code == 401
        # customer
        r2 = requests.post(f"{API}/products", headers=auth(customer["token"]),
                           json={"name": "x", "description": "x", "category": "pokecoin_bundle", "price": 1.0})
        assert r2.status_code == 403
        # anonymous PUT / DELETE
        assert requests.put(f"{API}/products/000000000000000000000000",
                            json={"name": "x", "description": "x",
                                  "category": "pokecoin_bundle", "price": 1.0}).status_code == 401
        assert requests.delete(f"{API}/products/000000000000000000000000").status_code == 401

    def test_admin_crud(self, admin_token):
        payload = {"name": "TEST_ProductX", "description": "desc",
                   "category": "pokecoin_bundle", "price": 1.99, "coins": 100}
        r = requests.post(f"{API}/products", headers=auth(admin_token), json=payload)
        assert r.status_code == 200, r.text
        pid = r.json()["id"]
        payload["name"] = "TEST_ProductX_upd"
        payload["price"] = 2.49
        r2 = requests.put(f"{API}/products/{pid}", headers=auth(admin_token), json=payload)
        assert r2.status_code == 200 and r2.json()["name"] == "TEST_ProductX_upd"
        r3 = requests.delete(f"{API}/products/{pid}", headers=auth(admin_token))
        assert r3.status_code == 200


# ---------------- Guest checkout ----------------
class TestGuestCheckout:
    def test_guest_checkout_requires_email(self):
        bundle = _find("pokecoin_bundle")
        r = requests.post(f"{API}/orders/checkout", json={
            "items": [{"product_id": bundle["id"], "quantity": 1}],
            "ptc_username": "u", "ptc_password": "p", "origin_url": BASE_URL,
        })
        assert r.status_code == 400
        assert "email" in r.json()["detail"].lower()

    def test_guest_checkout_success(self):
        bundle = _find("pokecoin_bundle")
        r = requests.post(f"{API}/orders/checkout", json={
            "items": [{"product_id": bundle["id"], "quantity": 1}],
            "ptc_username": "guest_user_plain", "ptc_password": "GuestSecret#42",
            "origin_url": BASE_URL, "email": f"guest_{uuid.uuid4().hex[:6]}@example.com",
        })
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["checkout_url"].startswith("http")
        assert data["order_id"] and data["session_id"]
        # ciphertext in DB, user_id blank
        doc = db.orders.find_one({"_id": ObjectId(data["order_id"])})
        assert doc["ptc_username_enc"].startswith("gAAAA")
        assert doc["ptc_password_enc"].startswith("gAAAA")
        assert doc.get("user_id", "") == ""
        pytest.guest_order_id = data["order_id"]

    def test_guest_cart_rule_still_enforced(self):
        pass_p = _find("event_pass")
        r = requests.post(f"{API}/orders/checkout", json={
            "items": [{"product_id": pass_p["id"], "quantity": 1}],
            "ptc_username": "u", "ptc_password": "p", "origin_url": BASE_URL,
            "email": "guest@example.com",
        })
        assert r.status_code == 400
        assert "Pok" in r.json()["detail"]

    def test_guest_can_read_own_order_and_post_messages(self):
        oid = pytest.guest_order_id
        # GET order (no auth)
        r = requests.get(f"{API}/orders/{oid}")
        assert r.status_code == 200
        # no plaintext / ciphertext leak
        assert "ptc_password" not in r.json()
        assert "ptc_password_enc" not in r.json()
        # messages list (no auth)
        assert requests.get(f"{API}/orders/{oid}/messages").status_code == 200
        # post message (no auth)
        rp = requests.post(f"{API}/orders/{oid}/messages", json={"body": "guest ping"})
        assert rp.status_code == 200, rp.text
        assert rp.json()["sender_role"] == "customer"

    def test_admin_can_reveal_guest_credentials(self, admin_token):
        oid = pytest.guest_order_id
        r = requests.get(f"{API}/admin/orders/{oid}/credentials", headers=auth(admin_token))
        assert r.status_code == 200
        assert r.json()["ptc_username"] == "guest_user_plain"
        assert r.json()["ptc_password"] == "GuestSecret#42"


# ---------------- Registered user checkout ----------------
class TestRegisteredCheckout:
    def test_bundle_and_pass_checkout_success(self, customer):
        bundle = _find("pokecoin_bundle")
        pass_p = _find("event_pass")
        r = requests.post(f"{API}/orders/checkout", headers=auth(customer["token"]), json={
            "items": [{"product_id": bundle["id"], "quantity": 1},
                      {"product_id": pass_p["id"], "quantity": 1}],
            "ptc_username": "trainer_plaintext_user",
            "ptc_password": "PlainSecretPwd#42",
            "origin_url": BASE_URL,
        })
        assert r.status_code == 200, r.text
        customer["order_id"] = r.json()["order_id"]
        doc = db.orders.find_one({"_id": ObjectId(customer["order_id"])})
        assert doc["user_id"] == customer["id"]
        assert doc["ptc_username_enc"].startswith("gAAAA")

    def test_event_pass_only_rejected(self, customer):
        pass_p = _find("event_pass")
        r = requests.post(f"{API}/orders/checkout", headers=auth(customer["token"]), json={
            "items": [{"product_id": pass_p["id"], "quantity": 1}],
            "ptc_username": "u", "ptc_password": "p", "origin_url": BASE_URL,
        })
        assert r.status_code == 400

    def test_shundo_coming_soon_rejected(self, customer):
        products = _products()
        shundo = next((p for p in products if p["category"] == "shundo_service"), None)
        assert shundo
        r = requests.post(f"{API}/orders/checkout", headers=auth(customer["token"]), json={
            "items": [{"product_id": shundo["id"], "quantity": 1}],
            "ptc_username": "u", "ptc_password": "p", "origin_url": BASE_URL,
        })
        assert r.status_code == 400


# ---------------- Order privacy (registered) ----------------
class TestOrderPrivacy:
    def test_owner_can_read(self, customer):
        oid = customer["order_id"]
        r = requests.get(f"{API}/orders/{oid}", headers=auth(customer["token"]))
        assert r.status_code == 200
        assert "ptc_password_enc" not in r.json()

    def test_other_user_forbidden(self, customer, customer2):
        oid = customer["order_id"]
        assert requests.get(f"{API}/orders/{oid}", headers=auth(customer2["token"])).status_code == 403

    def test_anonymous_forbidden_on_registered_order(self, customer):
        oid = customer["order_id"]
        assert requests.get(f"{API}/orders/{oid}").status_code == 403
        assert requests.get(f"{API}/orders/{oid}/messages").status_code == 403
        assert requests.post(f"{API}/orders/{oid}/messages", json={"body": "sneaky"}).status_code == 403

    def test_admin_can_read_registered_order(self, admin_token, customer):
        r = requests.get(f"{API}/orders/{customer['order_id']}", headers=auth(admin_token))
        assert r.status_code == 200

    def test_customer_cannot_reveal_creds(self, customer):
        assert requests.get(f"{API}/admin/orders/{customer['order_id']}/credentials",
                            headers=auth(customer["token"])).status_code == 403


# ---------------- Status updates & notifications ----------------
class TestStatusAndNotifications:
    def test_transitions_and_notify_registered(self, admin_token, customer):
        oid = customer["order_id"]
        r = requests.patch(f"{API}/admin/orders/{oid}/status", headers=auth(admin_token),
                           json={"status": "processing"})
        assert r.status_code == 200 and r.json()["status"] == "processing"
        time.sleep(0.3)
        notifs = requests.get(f"{API}/notifications", headers=auth(customer["token"])).json()
        assert any("processed" in n["title"].lower() or "logged out" in n["title"].lower() for n in notifs)
        r2 = requests.patch(f"{API}/admin/orders/{oid}/status", headers=auth(admin_token),
                            json={"status": "completed"})
        assert r2.status_code == 200
        notifs = requests.get(f"{API}/notifications", headers=auth(customer["token"])).json()
        assert any("completed" in n["title"].lower() for n in notifs)

    def test_guest_status_change_creates_no_notifications(self, admin_token):
        gid = pytest.guest_order_id
        before = db.notifications.count_documents({})
        r = requests.patch(f"{API}/admin/orders/{gid}/status", headers=auth(admin_token),
                           json={"status": "processing"})
        assert r.status_code == 200
        after = db.notifications.count_documents({})
        assert after == before  # no notification for guest orders

    def test_invalid_status(self, admin_token, customer):
        r = requests.patch(f"{API}/admin/orders/{customer['order_id']}/status",
                           headers=auth(admin_token), json={"status": "bogus"})
        assert r.status_code == 400


# ---------------- Admin endpoints protection ----------------
class TestAdminProtection:
    def test_admin_orders_requires_admin(self, customer):
        assert requests.get(f"{API}/admin/orders").status_code == 401
        assert requests.get(f"{API}/admin/orders", headers=auth(customer["token"])).status_code == 403

    def test_admin_can_list_orders(self, admin_token):
        r = requests.get(f"{API}/admin/orders", headers=auth(admin_token))
        assert r.status_code == 200 and isinstance(r.json(), list)


# ---------------- Chat (registered) ----------------
class TestChat:
    def test_customer_post_and_admin_reply(self, admin_token, customer):
        oid = customer["order_id"]
        r = requests.post(f"{API}/orders/{oid}/messages", headers=auth(customer["token"]),
                          json={"body": "Hi, when will this be picked up?"})
        assert r.status_code == 200
        r2 = requests.get(f"{API}/orders/{oid}/messages", headers=auth(admin_token))
        assert r2.status_code == 200
        assert any("picked up" in m["body"] for m in r2.json())
        r3 = requests.post(f"{API}/orders/{oid}/messages", headers=auth(admin_token),
                           json={"body": "On it now."})
        assert r3.status_code == 200
