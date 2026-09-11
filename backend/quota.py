"""Kuota menit -- fondasi billing. DUA mode (lihat .env.example):

GLOBAL (lama, tak berubah): DAILY_MINUTES_LIMIT utk seluruh server.
File jobs/quota.json {"YYYY-MM-DD": detik}. 0 = tanpa batas.
PER-USER (gap #6, MULTIUSER=1): {"YYYY-MM-DD": {"": detik_global,
"<api_key>": detik_user}} -- tiap user dibatasi plan-nya sendiri
(lihat accounts.PLANS). Format lama (int/hari) tetap terbaca sbg global.
"""
import json
import threading
from datetime import datetime, timezone

from . import config

_LOCK = threading.Lock()
_FILE = config.JOBS_DIR / "quota.json"


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _load() -> dict:
    try:
        return json.loads(_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save(data: dict):
    _FILE.write_text(json.dumps(data, indent=1), encoding="utf-8")


def _day_entry(data: dict, day: str) -> dict:
    """Entri hari, normalisasi: format v1 (int) dibaca sbg global ("")."""
    v = data.get(day)
    if isinstance(v, dict):
        return v
    return {"": int(v)} if v else {}


def used_seconds(day: str = None, user: str = None) -> int:
    """Detik terpakai hari ini / hari tertentu; bila `user` diisi -> milik user itu."""
    with _LOCK:
        return int(_day_entry(_load(), day or _today()).get(user or "", 0))


def allow(need_seconds: float) -> bool:
    """MODE GLOBAL: True kalau masih muat dalam DAILY_MINUTES_LIMIT hari ini."""
    if config.DAILY_MINUTES_LIMIT <= 0:
        return True  # tanpa batas
    return used_seconds() + need_seconds <= config.DAILY_MINUTES_LIMIT * 60


def add(seconds: float, user: str = None):
    """Catat pemakaian (dipanggil saat job SELESAI -- gagal tak dihitung).
    `user` diisi -> kuota user itu, bukan global."""
    with _LOCK:
        data = _load()
        day = _today()
        entry = _day_entry(data, day)
        k = user or ""
        entry[k] = int(entry.get(k, 0)) + max(0, int(seconds))
        data[day] = entry
        # gulung: buang hari tua biar file tak tumbuh selamanya
        if len(data) > 8:
            for k2 in sorted(data)[:-7]:
                data.pop(k2, None)
        _save(data)


def user_allow(user_key: str, plan_minutes: float, need_seconds: float) -> bool:
    """MODE PER-USER: True kalau masih muat dalam batas plan user hari ini.
    plan_minutes <= 0 = tanpa batas (plan unlimited)."""
    if plan_minutes <= 0:
        return True
    return (used_seconds(user=user_key) + need_seconds
            <= plan_minutes * 60)


def _usage(limit: float, used: int) -> dict:
    return {
        "limit_minutes": limit,
        "used_minutes": round(used / 60, 1),
        "left_minutes": (round(limit - used / 60, 1) if limit > 0 else None),
        "resets_at_utc": "00:00 UTC",
    }


def usage() -> dict:
    """MODE GLOBAL: bentuk utk /api/quota (perilaku lama)."""
    return _usage(config.DAILY_MINUTES_LIMIT, used_seconds())


def user_usage(user_key: str, plan_minutes: float) -> dict:
    """MODE PER-USER: kuota hari ini milik satu user."""
    return _usage(plan_minutes, used_seconds(user=user_key))
