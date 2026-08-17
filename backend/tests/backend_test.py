"""PokéForge backend end-to-end regression tests."""
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

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") if os.environ.get("REACT_APP_BACKEND_URL") else "https://digital-gaming-store-7.preview.emergentagent.com"
# Load frontend URL from frontend .env explicitly
try:
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
except Exception:
    pass

API = f"{BASE_URL}/api"
ADMIN_EMAIL = "admin@pokeforge.gg"
ADMIN_PASSWORD = "ForgeAdmin#2026"

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")
mongo = MongoClient(MONGO_URL)
db = mongo[DB_NAME]


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


def auth(token):
    return {"Authorization": f"Bearer {token}"}


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
        data = r.json()
        assert data["email"] == customer["email"]
        assert data["role"] == "customer"

    def test_login_wrong_password(self):
        throwaway = f"nobody_{uuid.uuid4().hex[:8]}@example.com"
        # register user then wrong pwd
        requests.post(f"{API}/auth/register", json={"email": throwaway, "password": "GoodPass#2026", "name": "X"})
        r = requests.post(f"{API}/auth/login", json={"email": throwaway, "password": "WrongPass!!"})
        assert r.status_code == 401

    def test_admin_login(self, admin_token):
        assert admin_token


# ---------------- Products ----------------
class TestProducts:
    def test_list_products(self):
        r = requests.get(f"{API}/products")
        assert r.status_code == 200
        products = r.json()
        assert len(products) >= 6
        categories = {p["category"] for p in products}
        assert {"pokecoin_bundle", "event_pass", "shundo_service"}.issubset(categories)
        # no mongo _id leakage
        for p in products:
            assert "_id" not in p
            assert "id" in p

    def test_non_admin_cannot_create(self, customer):
        r = requests.post(f"{API}/products", headers=auth(customer["token"]),
                          json={"name": "TEST_hack", "description": "x", "category": "pokecoin_bundle", "price": 1.0})
        assert r.status_code == 403

    def test_admin_crud(self, admin_token):
        payload = {"name": "TEST_ProductX", "description": "desc", "category": "pokecoin_bundle",
                   "price": 1.99, "coins": 100}
        r = requests.post(f"{API}/products", headers=auth(admin_token), json=payload)
        assert r.status_code == 200, r.text
        pid = r.json()["id"]
        # appears on storefront
        listing = requests.get(f"{API}/products").json()
        assert any(p["id"] == pid for p in listing)
        # update
        payload["name"] = "TEST_ProductX_upd"
        payload["price"] = 2.49
        r2 = requests.put(f"{API}/products/{pid}", headers=auth(admin_token), json=payload)
        assert r2.status_code == 200, r2.text
        assert r2.json()["name"] == "TEST_ProductX_upd"
        # delete
        r3 = requests.delete(f"{API}/products/{pid}", headers=auth(admin_token))
        assert r3.status_code == 200


# ---------------- Cart rule ----------------
class TestCheckout:
    def _find(self, category):
        products = requests.get(f"{API}/products").json()
        for p in products:
            if p["category"] == category and not p.get("coming_soon"):
                return p
        return None

    def test_event_pass_only_rejected(self, customer):
        pass_p = self._find("event_pass")
        assert pass_p
        r = requests.post(f"{API}/orders/checkout", headers=auth(customer["token"]),
                          json={"items": [{"product_id": pass_p["id"], "quantity": 1}],
                                "ptc_username": "trainer_x", "ptc_password": "SuperSecret1!",
                                "origin_url": BASE_URL})
        assert r.status_code == 400
        assert "Pokécoin Bundle" in r.json()["detail"] or "Pok" in r.json()["detail"]

    def test_checkout_success_bundle_and_pass(self, customer):
        bundle = self._find("pokecoin_bundle")
        pass_p = self._find("event_pass")
        r = requests.post(f"{API}/orders/checkout", headers=auth(customer["token"]),
                          json={"items": [{"product_id": bundle["id"], "quantity": 1},
                                          {"product_id": pass_p["id"], "quantity": 1}],
                                "ptc_username": "trainer_plaintext_user",
                                "ptc_password": "PlainSecretPwd#42",
                                "origin_url": BASE_URL})
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["checkout_url"].startswith("http")
        assert data["order_id"]
        customer["order_id"] = data["order_id"]
        # verify ciphertext in mongo
        doc = db.orders.find_one({"_id": ObjectId(data["order_id"])})
        assert doc is not None
        assert doc["ptc_username_enc"].startswith("gAAAA")
        assert doc["ptc_password_enc"].startswith("gAAAA")
        assert "trainer_plaintext_user" not in doc["ptc_username_enc"]

    def test_checkout_requires_auth(self):
        r = requests.post(f"{API}/orders/checkout",
                          json={"items": [], "ptc_username": "u", "ptc_password": "p", "origin_url": BASE_URL})
        assert r.status_code == 401

    def test_shundo_coming_soon_rejected(self, customer):
        shundo = self._find("shundo_service")
        if not shundo:
            # coming_soon products may be filtered? test data has coming_soon true
            products = requests.get(f"{API}/products").json()
            shundo = next((p for p in products if p["category"] == "shundo_service"), None)
        assert shundo
        r = requests.post(f"{API}/orders/checkout", headers=auth(customer["token"]),
                          json={"items": [{"product_id": shundo["id"], "quantity": 1}],
                                "ptc_username": "u", "ptc_password": "p", "origin_url": BASE_URL})
        assert r.status_code == 400


# ---------------- Orders & PTC leak ----------------
class TestOrdersAndCredentials:
    def test_my_orders_no_plaintext_leak(self, customer):
        r = requests.get(f"{API}/orders", headers=auth(customer["token"]))
        assert r.status_code == 200
        orders = r.json()
        assert len(orders) >= 1
        for o in orders:
            assert "ptc_username_enc" not in o
            assert "ptc_password_enc" not in o
            assert o.get("ptc_username") is None or "plaintext" not in str(o.get("ptc_username", ""))
            assert "_id" not in o

    def test_get_order_no_leak(self, customer):
        oid = customer.get("order_id")
        assert oid
        r = requests.get(f"{API}/orders/{oid}", headers=auth(customer["token"]))
        assert r.status_code == 200
        data = r.json()
        assert "ptc_password" not in data
        assert "ptc_password_enc" not in data

    def test_other_customer_forbidden(self, customer, customer2):
        oid = customer["order_id"]
        r = requests.get(f"{API}/orders/{oid}", headers=auth(customer2["token"]))
        assert r.status_code == 403

    def test_customer_cannot_reveal_credentials(self, customer):
        oid = customer["order_id"]
        r = requests.get(f"{API}/admin/orders/{oid}/credentials", headers=auth(customer["token"]))
        assert r.status_code == 403

    def test_admin_reveal_credentials(self, admin_token, customer):
        oid = customer["order_id"]
        r = requests.get(f"{API}/admin/orders/{oid}/credentials", headers=auth(admin_token))
        assert r.status_code == 200
        data = r.json()
        assert data["ptc_username"] == "trainer_plaintext_user"
        assert data["ptc_password"] == "PlainSecretPwd#42"


# ---------------- Status updates & notifications ----------------
class TestStatusAndNotifications:
    def test_status_transitions_and_notifications(self, admin_token, customer):
        oid = customer["order_id"]
        # processing
        r = requests.patch(f"{API}/admin/orders/{oid}/status", headers=auth(admin_token),
                           json={"status": "processing"})
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "processing"
        time.sleep(0.3)
        notifs = requests.get(f"{API}/notifications", headers=auth(customer["token"])).json()
        assert any("STAY LOGGED OUT" in n["title"] or "processed" in n["title"].lower() for n in notifs)
        # completed
        r2 = requests.patch(f"{API}/admin/orders/{oid}/status", headers=auth(admin_token),
                            json={"status": "completed"})
        assert r2.status_code == 200
        assert r2.json()["status"] == "completed"
        notifs = requests.get(f"{API}/notifications", headers=auth(customer["token"])).json()
        assert any("completed" in n["title"].lower() for n in notifs)

    def test_invalid_status(self, admin_token, customer):
        oid = customer["order_id"]
        r = requests.patch(f"{API}/admin/orders/{oid}/status", headers=auth(admin_token),
                           json={"status": "bogus"})
        assert r.status_code == 400


# ---------------- Chat ----------------
class TestChat:
    def test_customer_post_and_admin_reply(self, admin_token, customer, customer2):
        oid = customer["order_id"]
        r = requests.post(f"{API}/orders/{oid}/messages", headers=auth(customer["token"]),
                          json={"body": "Hi, when will this be picked up?"})
        assert r.status_code == 200, r.text
        # admin lists messages
        r2 = requests.get(f"{API}/orders/{oid}/messages", headers=auth(admin_token))
        assert r2.status_code == 200
        msgs = r2.json()
        assert any("picked up" in m["body"] for m in msgs)
        # admin reply
        r3 = requests.post(f"{API}/orders/{oid}/messages", headers=auth(admin_token),
                           json={"body": "On it now, please stay logged out."})
        assert r3.status_code == 200
        # customer sees admin reply and gets notification
        msgs2 = requests.get(f"{API}/orders/{oid}/messages", headers=auth(customer["token"])).json()
        assert any(m["sender_role"] == "admin" for m in msgs2)
        notifs = requests.get(f"{API}/notifications", headers=auth(customer["token"])).json()
        assert any("support" in n["title"].lower() or "message" in n["title"].lower() for n in notifs)

    def test_other_customer_forbidden_from_messages(self, customer, customer2):
        oid = customer["order_id"]
        r = requests.get(f"{API}/orders/{oid}/messages", headers=auth(customer2["token"]))
        assert r.status_code == 403
        r2 = requests.post(f"{API}/orders/{oid}/messages", headers=auth(customer2["token"]),
                           json={"body": "sneaky"})
        assert r2.status_code == 403


# ---------------- Admin orders ----------------
class TestAdminOrders:
    def test_admin_can_list_all_orders(self, admin_token):
        r = requests.get(f"{API}/admin/orders", headers=auth(admin_token))
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_customer_cannot_access_admin_orders(self, customer):
        r = requests.get(f"{API}/admin/orders", headers=auth(customer["token"]))
        assert r.status_code == 403
