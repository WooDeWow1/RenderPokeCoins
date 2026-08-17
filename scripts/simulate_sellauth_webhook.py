"""Simulate a SellAuth paid webhook against the local backend (dev verification only)."""
import hashlib
import hmac
import json
import os
import sys

import httpx
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")

BASE = "http://localhost:8001"
secret = os.environ["SELLAUTH_WEBHOOK_SECRET"]

session_id = sys.argv[1]
invoice = {
    "id": f"probe-invoice-{session_id[-6:]}",
    "status": "completed",
    "custom_fields": {"checkout_session_id": session_id},
}
raw = json.dumps({"invoice": invoice}).encode()
sig = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()

bad = httpx.post(f"{BASE}/api/webhooks/sellauth", content=raw,
                 headers={"signature": "00" * 32, "content-type": "application/json"})
print("bad signature ->", bad.status_code, bad.text[:120])

good = httpx.post(f"{BASE}/api/webhooks/sellauth", content=raw,
                  headers={"signature": sig, "content-type": "application/json"}, timeout=60)
print("good signature ->", good.status_code, good.text[:300])

replay = httpx.post(f"{BASE}/api/webhooks/sellauth", content=raw,
                    headers={"signature": sig, "content-type": "application/json"}, timeout=60)
print("replay ->", replay.status_code, replay.text[:200])
