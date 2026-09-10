"""Kuota harian (menit) — fondasi billing; tanpa ini, deploy publik = orang
asing bisa memakai Gemini & CPU kita gratis selamanya.

File state: jobs/quota.json  {"YYYY-MM-DD": detik_terpakai}
DAILY_MINUTES_LIMIT = 0 -> tanpa batas (mode lokal lama, perilaku tak berubah).
"""
import json
import threading
import time
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


def used_seconds(day: str = None) -> int:
    """Detik terpakai hari ini (default) / hari tertentu."""
    with _LOCK:
        return int(_load().get(day or _today(), 0))


def allow(need_seconds: float) -> bool:
    """True kalau video `need_seconds` masih muat dalam kuota hari ini."""
    if config.DAILY_MINUTES_LIMIT <= 0:
        return True  # tanpa batas
    return used_seconds() + need_seconds <= config.DAILY_MINUTES_LIMIT * 60


def add(seconds: float):
    """Catat pemakaian (dipanggil saat job SELESAI — gagal tidak dihitung)."""
    with _LOCK:
        data = _load()
        day = _today()
        data[day] = int(data.get(day, 0)) + max(0, int(seconds))
        # gulung: buang hari tua (> 7 hari) biar file tak tumbuh selamanya
        if len(data) > 8:
            for k in sorted(data)[:-7]:
                data.pop(k, None)
        _save(data)


def usage() -> dict:
    """Bentuk untuk /api/quota: {limit_menit, terpakai_menit, sisa_menit}."""
    limit = config.DAILY_MINUTES_LIMIT
    used = used_seconds()
    return {
        "limit_minutes": limit,
        "used_minutes": round(used / 60, 1),
        "left_minutes": (round(limit - used / 60, 1) if limit > 0 else None),
        "resets_at_utc": "00:00 UTC",
    }
