"""Uji lapisan siap-produk: kuota harian, pemulihan job basi, auth ringan."""
import json

import pytest

from backend import config, pipeline, quota


def _set_limit(monkeypatch, minutes):
    monkeypatch.setattr(config, "DAILY_MINUTES_LIMIT", float(minutes))


def test_quota_unlimited_when_limit_zero(monkeypatch):
    _set_limit(monkeypatch, 0)
    assert quota.allow(999_999) is True
    assert quota.usage()["left_minutes"] is None


def test_quota_blocks_when_exceeded(monkeypatch, tmp_path):
    _set_limit(monkeypatch, 10)  # 10 menit
    monkeypatch.setattr(quota, "_FILE", tmp_path / "quota.json")
    assert quota.allow(9 * 60) is True
    quota.add(9 * 60)
    assert quota.allow(2 * 60) is False   # sisa 1 menit < 2 menit
    assert quota.allow(0.5 * 60) is True
    quota.add(0.5 * 60)
    u = quota.usage()
    assert u["used_minutes"] == 9.5 and u["left_minutes"] == 0.5


def test_quota_rolls_old_days(tmp_path, monkeypatch):
    """File kuota tidak boleh tumbuh selamanya."""
    _set_limit(monkeypatch, 100)
    monkeypatch.setattr(quota, "_FILE", tmp_path / "quota.json")
    for day in ("2020-01-01", "2020-01-02", "2020-01-03", "2020-01-04"):
        (tmp_path / "quota.json").write_text(json.dumps({day: 60}))
        quota.add(60)  # hari ini
    data = json.loads((tmp_path / "quota.json").read_text())
    assert "2020-01-01" not in data  # hari tua digulung
    assert len(data) <= 7


def test_recover_stale_jobs_marks_them_error(tmp_path, monkeypatch):
    """Job sisa server mati (running/queued) -> error jelas saat startup baru."""
    monkeypatch.setattr(config, "JOBS_DIR", tmp_path)
    monkeypatch.setattr(config, "LOGS_DIR", tmp_path)
    for st in ("running", "queued", "done", "error"):
        (tmp_path / f"job_{st}.json").write_text(json.dumps({"id": st, "status": st}))
    n = pipeline.recover_stale_jobs()
    assert n == 2
    assert json.loads((tmp_path / "job_running.json").read_text())["status"] == "error"
    assert json.loads((tmp_path / "job_queued.json").read_text())["status"] == "error"
    assert json.loads((tmp_path / "job_done.json").read_text())["status"] == "done"
    assert json.loads((tmp_path / "job_error.json").read_text())["status"] == "error"


def test_recover_survives_corrupt_json(tmp_path, monkeypatch):
    """File json rusak tidak boleh menggagalkan startup."""
    monkeypatch.setattr(config, "JOBS_DIR", tmp_path)
    monkeypatch.setattr(config, "LOGS_DIR", tmp_path)
    (tmp_path / "j1.json").write_text("{bukan json")
    (tmp_path / "j2.json").write_text(json.dumps({"id": "x", "status": "running"}))
    assert pipeline.recover_stale_jobs() == 1


def test_auth_rejects_wrong_key(monkeypatch):
    from fastapi.testclient import TestClient
    from backend import main
    monkeypatch.setattr(config, "API_KEY", "rahasia-123")
    client = TestClient(main.app)
    r = client.post("/api/clip", json={"url": "https://x.com/v/1"})
    assert r.status_code == 401
    r = client.post("/api/clip", json={"url": "https://x.com/v/1"},
                    headers={"X-API-Key": "salah"})
    assert r.status_code == 401
    # kunci benar -> lewat gembok (gagal validasi URL, bukan auth)
    r = client.post("/api/clip", json={"url": "https://x.com/v/1"},
                    headers={"X-API-Key": "rahasia-123"})
    assert r.status_code != 401


def test_auth_off_local_mode(monkeypatch):
    """API_KEY kosong = perilaku lokal lama: semua request bebas."""
    from fastapi.testclient import TestClient
    from backend import main
    monkeypatch.setattr(config, "API_KEY", "")
    client = TestClient(main.app)
    r = client.get("/api/health")
    assert r.status_code == 200 and r.json()["auth"] is False
