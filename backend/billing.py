"""Billing (gap #6): order + Midtrans SNAP bila server key terpasang, ATAU
MODE MANUAL (tanpa payment gateway): order dibuat, pembeli transfer bank,
admin grant lewat POST /api/billing/grant -- bisa jualan HARI INI tanpa
menunggu approve gateway.
File state: jobs/orders.json (jobs/ sudah di-.gitignore). Webhook Midtrans
diverifikasi signature SHA-512 (order_id+status_code+gross_amount+server_key).
"""
import base64
import hashlib
import json
import secrets
import threading
import urllib.request
from datetime import datetime, timezone

from . import accounts, config

_LOCK = threading.Lock()
_FILE = config.JOBS_DIR / "orders.json"


def _load() -> dict:
    try:
        return json.loads(_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save(data: dict):
    _FILE.write_text(json.dumps(data, indent=1), encoding="utf-8")


def gateway() -> str:
    return "midtrans" if config.MIDTRANS_SERVER_KEY else "manual"


def create_order(user: dict, plan: str, days: int = 30) -> dict:
    if plan not in accounts.PLANS or plan == "free":
        raise ValueError("Plan tidak valid untuk dibeli.")
    days = max(1, int(days))
    amount = config.PLAN_PRO_PRICE_IDR if plan == "pro" else 0
    order_id = ("SNOOPY-"
                + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
                + "-" + secrets.token_hex(3).upper())
    order = {
        "order_id": order_id, "email": user["email"], "plan": plan,
        "days": days, "amount_idr": amount, "status": "pending",
        "payment_url": None, "created": datetime.now(timezone.utc).isoformat(),
    }
    if config.MIDTRANS_SERVER_KEY:
        try:
            order["payment_url"] = _midtrans_snap(order)
            order["status"] = "pending_payment"
        except Exception as e:
            print(f"[billing] Midtrans tak terjangkau/gagal ({e}) "
                  f"-- order jatuh ke mode manual.", flush=True)
            order["status"] = "awaiting_manual"
    else:
        order["status"] = "awaiting_manual"
    with _LOCK:
        data = _load()
        data[order_id] = order
        _save(data)
    return order


def _midtrans_snap(order: dict) -> str:
    base = ("https://app.midtrans.com" if config.MIDTRANS_IS_PRODUCTION
            else "https://app.sandbox.midtrans.com")
    payload = {
        "transaction_details": {"order_id": order["order_id"],
                                "gross_amount": order["amount_idr"]},
        "item_details": [{"id": order["plan"], "price": order["amount_idr"],
                          "quantity": 1,
                          "name": f"Snoopy {order['plan']} {order['days']} hari"}],
        "customer_details": {"email": order["email"]},
    }
    req = urllib.request.Request(
        base + "/snap/v1/transactions",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "Accept": "application/json",
                 "Authorization": "Basic " + base64.b64encode(
                     (config.MIDTRANS_SERVER_KEY + ":").encode()).decode()})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())["redirect_url"]


def verify_signature(order_id: str, status_code: str, gross_amount: str,
                     signature: str) -> bool:
    raw = f"{order_id}{status_code}{gross_amount}{config.MIDTRANS_SERVER_KEY}"
    return hashlib.sha512(raw.encode()).hexdigest() == (signature or "").lower()


def handle_notification(payload: dict) -> dict:
    """Webhook Midtrans (HTTP notification). ValueError bila tak valid."""
    order_id = str(payload.get("order_id") or "")
    status_code = str(payload.get("status_code") or "")
    gross = str(payload.get("gross_amount") or "")
    sig = str(payload.get("signature_key") or "")
    if not order_id or not verify_signature(order_id, status_code, gross, sig):
        raise ValueError("Signature Midtrans tidak valid.")
    with _LOCK:
        data = _load()
        order = data.get(order_id)
        if not order:
            raise ValueError("Order tidak ditemukan.")
        tr = (payload.get("transaction_status") or "").lower()
        fraud = (payload.get("fraud_status") or "").lower()
        if (tr in ("settlement", "capture") and fraud != "challenge"
                and order["status"] != "paid"):
            order["status"] = "paid"
            order["paid_at"] = datetime.now(timezone.utc).isoformat()
            accounts.grant(order["email"], order["plan"], order["days"])
            order["granted"] = True
        elif tr == "pending":
            order["status"] = "pending_payment"
        elif tr in ("expire", "cancel", "deny"):
            order["status"] = "cancelled"
        _save(data)
        return order
