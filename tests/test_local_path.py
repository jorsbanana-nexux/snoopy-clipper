"""Jalur FILE LOKAL (rancangan awal: clip tanpa unduhan, file sudah di disk).
Bug ditemukan saat uji total 2026-09-11: create_job mewajibkan `url` padahal
docstring bilang 'url ATAU local_path' — fitur lokal tak pernah bisa dipanggil
(via CLI/API/pipeline). Fix: url jadi opsional + endpoint /api/clip terima
local_path (validasi file ada, 400 kalau tidak)."""
import json

from backend import config, main, pipeline
from fastapi.testclient import TestClient


def test_create_job_local_tanpa_url(tmp_path, monkeypatch):
    """create_job(local_path=...) harus jalan TANPA url — download dilewati,
    tampilan url = 'local:<path>'."""
    import backend.pipeline as pl
    called = {}
    monkeypatch.setattr(pl.downloader, "get_info_local",
                        lambda p: called.setdefault("info", True) or
                        {"duration": 60.0, "title": "Lokal", "uploader": "A"})
    monkeypatch.setattr(pl, "_run", lambda jid: None)   # worker tak dibutuhkan
    src = tmp_path / "video.mp4"
    src.write_bytes(b"fake")
    jid = pl.create_job(local_path=str(src))
    job = json.loads((config.JOBS_DIR / f"{jid}.json").read_text(encoding="utf-8"))
    assert job["local_path"] == str(src)
    assert job["url"] == f"local:{src}"
    assert job["status"] == "queued"


def test_api_clip_terima_local_path(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "API_KEY", "")
    client = TestClient(main.app)
    src = tmp_path / "v.mp4"
    src.write_bytes(b"x")
    monkeypatch.setattr(pipeline, "create_job",
                        lambda url=None, local_path=None: "stub123")
    r = client.post("/api/clip", json={"local_path": str(src)})
    assert r.status_code == 200 and r.json() == {"job_id": "stub123"}


def test_api_clip_local_file_hilang_400(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "API_KEY", "")
    client = TestClient(main.app)
    r = client.post("/api/clip",
                    json={"local_path": str(tmp_path / "tidak_ada.mp4")})
    assert r.status_code == 400 and "tidak ditemukan" in r.text


def test_api_clip_tanpa_url_dan_local_400(monkeypatch):
    monkeypatch.setattr(config, "API_KEY", "")
    client = TestClient(main.app)
    r = client.post("/api/clip", json={})
    assert r.status_code == 400
