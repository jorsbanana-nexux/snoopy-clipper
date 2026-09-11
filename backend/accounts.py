"""Akun multi-user (gap #6 siap-produk): registrasi/login ringan + kunci API per-user.

Desain — TANPA dependensi baru (stdlib saja):
- Password TIDAK disimpan: PBKDF2-HMAC-SHA256 (120k iterasi) + salt acak.
- Kunci API per-user (sk_...) = kredensial permanen; frontend menyimpannya
  (mekanisme X-API-Key tier-1 tetap dipakai, tak ada perombakan besar).
- Plan: free / pro -- batas menit/hari dari config (PLAN_* di .env).
- Admin (ADMIN_EMAIL di .env) dapat grant plan manual: mode jualan TANPA
  payment gateway -- pembeli transfer bank, admin aktifkan, selesai.
- File state: jobs/users.json (jobs/ sudah di-.gitignore).
MULTIUSER=0 (default) -> modul ini tidak dipakai server; perilaku lokal tak berubah.
"""
import hashlib
import json
import re
import secrets
import threading
from datetime import datetime, timedelta, timezone

from . import config

_LOCK = threading.Lock()
_FILE = config.JOBS_DIR / "users.json"
_PBKDF2_ITER = 120_000
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

PLANS = {
    "free": {"label": "Free", "daily_minutes": config.PLAN_FREE_DAILY_MINUTES},
    "pro": {"label": "Pro", "daily_minutes": config.PLAN_PRO_DAILY_MINUTES},
}


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _load() -> dict:
    try:
        return json.loads(_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save(data: dict):
    _FILE.write_text(json.dumps(data, indent=1), encoding="utf-8")


def _hash(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", (password or "").encode(), bytes.fromhex(salt), _PBKDF2_ITER).hex()


def _validate(email: str, password: str) -> str:
    email = (email or "").strip().lower()
    if not _EMAIL_RE.match(email):
        raise ValueError("Email tidak valid.")
    if len(password or "") < 8:
        raise ValueError("Password minimal 8 karakter.")
    return email


def register(email: str, password: str) -> dict:
    email = _validate(email, password)
    with _LOCK:
        data = _load()
        if email in data:
            raise ValueError("Email sudah terdaftar -- login saja.")
        salt = secrets.token_hex(16)
        user = {
            "email": email,
            "salt": salt,
            "pwhash": _hash(password, salt),
            "api_key": "sk_" + secrets.token_hex(16),
            "plan": "free",
            "plan_expires": None,
            "admin": email == (config.ADMIN_EMAIL or "").strip().lower(),
            "created": datetime.now(timezone.utc).isoformat(),
        }
        data[email] = user
        _save(data)
    return user


def login(email: str, password: str):
    email = (email or "").strip().lower()
    with _LOCK:
        user = _load().get(email)
    if not user or not user.get("pwhash") or \
            _hash(password, user["salt"]) != user["pwhash"]:
        return None  # akun google-only tak bisa login via password
    return user


def get(email: str):
    with _LOCK:
        return _load().get((email or "").strip().lower())


def get_by_key(api_key: str):
    if not api_key:
        return None
    with _LOCK:
        for u in _load().values():
            if u.get("api_key") == api_key:
                return u
    return None


def is_admin(user) -> bool:
    return bool(user and user.get("admin"))


def grant(email: str, plan: str, days: int = 30) -> dict:
    """Aktifkan plan utk user. Plan berbayar dihitung dari HARI INI + days
    (re-grant memperbarui masa aktif, tidak diakumulasi)."""
    if plan not in PLANS:
        raise ValueError(f"Plan tidak dikenal: {plan}")
    days = max(1, int(days))
    with _LOCK:
        data = _load()
        user = data.get((email or "").strip().lower())
        if not user:
            raise ValueError("User tidak ditemukan.")
        if plan == "free":
            user["plan"], user["plan_expires"] = "free", None
        else:
            user["plan"] = plan
            user["plan_expires"] = (datetime.now(timezone.utc).date()
                                    + timedelta(days=days)).isoformat()
        _save(data)
        return user


def effective_plan(user) -> str:
    plan = user.get("plan", "free") if user else "free"
    if plan != "free":
        exp = user.get("plan_expires")
        if not exp or _today() > exp:
            return "free"  # kedaluwarsa -> otomatis turun ke free
    return plan


def plan_minutes(user) -> float:
    return PLANS[effective_plan(user)]["daily_minutes"]


def public(user) -> dict:
    eff = effective_plan(user)
    return {
        "email": user["email"],
        "plan": eff,
        "plan_label": PLANS[eff]["label"],
        "plan_expires": user.get("plan_expires"),
        "daily_minutes": PLANS[eff]["daily_minutes"],
        "admin": is_admin(user),
    }


def upsert_google(email: str) -> dict:
    """Login via Google: user dg email itu sudah ada -> dipakai (ditautkan);
    belum ada -> akun BARU tanpa password (login hanya via Google).
    Email diverifikasi penuh oleh Google sebelum sampai sini (lihat main.py)."""
    email = (email or "").strip().lower()
    if not _EMAIL_RE.match(email):
        raise ValueError("Email Google tidak valid.")
    with _LOCK:
        data = _load()
        user = data.get(email)
        if not user:
            user = {
                "email": email, "salt": secrets.token_hex(16), "pwhash": None,
                "api_key": "sk_" + secrets.token_hex(16),
                "plan": "free", "plan_expires": None,
                "admin": email == (config.ADMIN_EMAIL or "").strip().lower(),
                "google": True,
                "created": datetime.now(timezone.utc).isoformat(),
            }
            data[email] = user
            _save(data)
        elif not user.get("google"):
            user["google"] = True  # tautkan ke akun email+password yang ada
            _save(data)
        return user
