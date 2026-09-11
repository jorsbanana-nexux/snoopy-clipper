"""Gap #6: akun multi-user + billing (Midtrans/manual) + kuota per-user.
Kontrak paling penting: MULTIUSER=0 -> perilaku lama TIDAK berubah sama sekali."""
import hashlib
import json

import pytest
from fastapi.testclient import TestClient

from backend import accounts, billing, config, quota
from backend.main import app


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(accounts, "_FILE", tmp_path / "users.json")
    monkeypatch.setattr(billing, "_FILE", tmp_path / "orders.json")
    monkeypatch.setattr(quota, "_FILE", tmp_path / "quota.json")
    monkeypatch.setattr(config, "MULTIUSER", True)
    monkeypatch.setattr(config, "MIDTRANS_SERVER_KEY", "")
    monkeypatch.setattr(config, "ADMIN_EMAIL", "bos@x.id")
    yield


client = TestClient(app)


def _register(email="a@x.id", pw="rahasia123"):
    r = client.post("/api/auth/register", json={"email": email, "password": pw})
    assert r.status_code == 200, r.text
    return r.json()


def test_register_login_dan_password_tidak_plaintext():
    out = _register()
    assert out["plan"] == "free" and out["api_key"].startswith("sk_")
    disk = json.loads(accounts._FILE.read_text())
    u = disk["a@x.id"]
    assert "rahasia123" not in json.dumps(u)          # password tak pernah plaintext
    assert u["pwhash"] and u["salt"]
    r = client.post("/api/auth/login",
                    json={"email": "a@x.id", "password": "rahasia123"})
    assert r.status_code == 200 and r.json()["api_key"] == out["api_key"]
    r = client.post("/api/auth/login",
                    json={"email": "a@x.id", "password": "salah12345"})
    assert r.status_code == 401
    with pytest.raises(ValueError):
        accounts.register("a@x.id", "rahasia123")     # duplikat
    with pytest.raises(ValueError):
        accounts.register("bukan-email", "rahasia123")
    with pytest.raises(ValueError):
        accounts.register("b@x.id", "short")         # password < 8


def test_kunci_tak_dikenal_ditolak():
    r = client.get("/api/me", headers={"X-API-Key": "sk_nope"})
    assert r.status_code == 401


def test_grant_dan_kedaluwarsa_otomatis_turun_free(monkeypatch):
    accounts.register("c@x.id", "rahasia1234")
    assert accounts.plan_minutes(accounts.get("c@x.id")) == config.PLAN_FREE_DAILY_MINUTES
    accounts.grant("c@x.id", "pro", 30)
    assert accounts.effective_plan(accounts.get("c@x.id")) == "pro"
    assert accounts.plan_minutes(accounts.get("c@x.id")) == config.PLAN_PRO_DAILY_MINUTES
    monkeypatch.setattr(accounts, "_today", lambda: "2030-01-01")  # masa depan
    assert accounts.effective_plan(accounts.get("c@x.id")) == "free"


def test_kuota_per_user_dan_format_v1_tetap_terbaca():
    quota._FILE.write_text(json.dumps({"2026-01-01": 100}))  # format lama (int)
    assert quota.used_seconds("2026-01-01") == 100
    assert quota.user_allow("sk_a", 30, 30 * 60)             # 30 menit pertama lolos
    quota.add(30 * 60, user="sk_a")
    assert not quota.user_allow("sk_a", 30, 60)             # habis -> tolak
    assert quota.user_allow("sk_b", 30, 60)                 # user lain tak terpengaruh
    u = quota.user_usage("sk_a", 30)
    assert u["used_minutes"] == 30.0 and u["left_minutes"] == 0.0
    assert quota.user_allow("sk_a", 0, 99999)               # plan unlimited


def test_checkout_manual_lalu_admin_grant():
    out = _register()
    key = {"X-API-Key": out["api_key"]}
    assert client.get("/api/me", headers=key).json()["plan"] == "free"
    plans = client.get("/api/billing/plans", headers=key).json()
    assert plans["gateway"] == "manual"
    co = client.post("/api/billing/checkout", json={"plan": "pro", "days": 30},
                     headers=key).json()
    assert co["status"] == "awaiting_manual" and co["payment_url"] is None
    assert "manual_instructions" in co
    r = client.post("/api/billing/grant",
                    json={"email": "a@x.id", "plan": "pro", "days": 30},
                    headers=key)
    assert r.status_code == 403                            # bukan admin -> tolak
    bos = _register("bos@x.id")
    r = client.post("/api/billing/grant",
                    json={"email": "a@x.id", "plan": "pro", "days": 30},
                    headers={"X-API-Key": bos["api_key"]})
    assert r.status_code == 200
    assert client.get("/api/me", headers=key).json()["plan"] == "pro"


def test_webhook_midtrans_grant_setelah_bayar(monkeypatch):
    monkeypatch.setattr(config, "MIDTRANS_SERVER_KEY", "SB-Mid-server-fake")
    out = _register()
    user = accounts.get("a@x.id")
    order = billing.create_order(user, "pro", 30)
    assert order["status"] == "awaiting_manual"  # snap key palsu -> jatuh manual
    gross = str(order["amount_idr"])
    sig = hashlib.sha512((order["order_id"] + "200" + gross
                          + "SB-Mid-server-fake").encode()).hexdigest()
    r = client.post("/api/billing/midtrans-webhook", json={
        "order_id": order["order_id"], "status_code": "200",
        "gross_amount": gross, "transaction_status": "settlement",
        "fraud_status": "accept", "signature_key": sig})
    assert r.status_code == 200, r.text
    assert accounts.effective_plan(accounts.get("a@x.id")) == "pro"
    r = client.post("/api/billing/midtrans-webhook", json={   # signature salah -> 403
        "order_id": order["order_id"], "status_code": "200",
        "gross_amount": gross, "transaction_status": "settlement",
        "signature_key": "deadbeef"})
    assert r.status_code == 403


def test_mode_lokal_tak_berubah(monkeypatch):
    monkeypatch.setattr(config, "MULTIUSER", False)
    assert client.get("/api/health").json()["multiuser"] is False
    r = client.get("/api/quota")          # tanpa kunci, mode lokal bebas
    assert r.status_code == 200
    r = client.get("/api/me", headers={"X-API-Key": "x"})
    assert r.status_code == 403           # endpoint akun nonaktif di mode lokal


def test_create_clip_membawa_akun_pemesan(monkeypatch):
    from backend import pipeline
    out = _register()
    calls = []
    monkeypatch.setattr(
        pipeline, "create_job",
        lambda url, user_key=None, plan_minutes=None:
            calls.append((url, user_key, plan_minutes)) or "job123")
    r = client.post("/api/clip", json={"url": "https://youtu.be/abc"},
                    headers={"X-API-Key": out["api_key"]})
    assert r.status_code == 200 and r.json()["job_id"] == "job123"
    assert calls[0][1] == out["api_key"]  # job melekat ke akun, bukan global
    assert calls[0][2] == config.PLAN_FREE_DAILY_MINUTES
