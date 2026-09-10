"""Uji auto-post YouTube: URL izin, tukar kode, unggahan 2 tahap (semua di-mock)."""
import json

from backend import config, publisher


def test_authorize_url_minimal_scope(monkeypatch):
    monkeypatch.setattr(config, "YT_CLIENT_ID", "cid-123")
    monkeypatch.setattr(config, "YT_CLIENT_SECRET", "sec")
    monkeypatch.setattr(config, "YT_REDIRECT_URI", "http://localhost:8000/api/publish/callback")
    url = publisher.authorize_url()
    assert "client_id=cid-123" in url
    assert "youtube.upload" in url          # scope minimal — cuma upload
    assert "access_type=offline" in url     # refresh token long-lived
    assert "prompt=consent" in url


def test_exchange_code_saves_refresh_token(monkeypatch, tmp_path):
    monkeypatch.setattr(publisher, "_TOKEN_PATH", tmp_path / "yt.json")
    monkeypatch.setattr(config, "YT_CLIENT_ID", "cid")
    monkeypatch.setattr(config, "YT_CLIENT_SECRET", "sec")
    monkeypatch.setattr(publisher, "_http_json",
                        lambda url, data: {"refresh_token": "r1", "access_token": "a1",
                                           "expires_in": 3599})
    publisher.exchange_code("code-xyz")
    tok = json.loads((tmp_path / "yt.json").read_text())
    assert tok["refresh_token"] == "r1"


def test_exchange_requires_refresh_token(monkeypatch, tmp_path):
    """Tanpa prompt=consent Google kadang tak kirim refresh_token — harus jelas err-nya."""
    monkeypatch.setattr(publisher, "_TOKEN_PATH", tmp_path / "yt.json")
    monkeypatch.setattr(config, "YT_CLIENT_ID", "cid")
    monkeypatch.setattr(config, "YT_CLIENT_SECRET", "sec")
    monkeypatch.setattr(publisher, "_http_json", lambda url, data: {"access_token": "a1"})
    import pytest
    with pytest.raises(RuntimeError, match="refresh token"):
        publisher.exchange_code("c")


def test_upload_two_stage_resumable(monkeypatch, tmp_path):
    clip = tmp_path / "clip_01.mp4"
    clip.write_bytes(b"MP4BYTES")
    calls = {}

    class R:  # respons urlopen palsu
        def __init__(self, headers=None, body=b"{}"):
            self.headers = headers or {}
            self._body = body
        def read(self):
            return self._body
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout=None):
        if req.method == "POST":          # tahap 1: minta Location
            calls["meta"] = json.loads(req.data.decode())
            calls["auth1"] = req.headers.get("Authorization")
            return R(headers={"Location": "https://up/session1"})
        calls["bytes"] = req.data         # tahap 2: PUT bytes
        return R(body=json.dumps({"id": "vidABC"}).encode())

    monkeypatch.setattr(config, "YT_CLIENT_ID", "cid")
    monkeypatch.setattr(config, "YT_CLIENT_SECRET", "sec")
    monkeypatch.setattr(publisher, "_TOKEN_PATH", tmp_path / "yt.json")
    (tmp_path / "yt.json").write_text(json.dumps(
        {"refresh_token": "r", "access_token": "tok", "expires_in": 3599, "saved_at": 0}))
    monkeypatch.setattr(publisher, "access_token", lambda: "tok")
    monkeypatch.setattr(config, "PUBLISH_PRIVACY", "unlisted")
    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    url = publisher.upload_clip(clip, "Judul Klip", "deskripsi #shorts")
    assert url == "https://youtu.be/vidABC"
    assert calls["meta"]["snippet"]["title"] == "Judul Klip"
    assert calls["meta"]["status"]["privacyStatus"] == "unlisted"
    assert calls["auth1"] == "Bearer tok"
    assert calls["bytes"] == b"MP4BYTES"


def test_publish_authorize_endpoint_requires_config(monkeypatch):
    from fastapi.testclient import TestClient
    from backend import main
    monkeypatch.setattr(config, "API_KEY", "")
    monkeypatch.setattr(config, "YT_CLIENT_ID", "")
    monkeypatch.setattr(config, "YT_CLIENT_SECRET", "")
    client = TestClient(main.app)
    r = client.get("/api/publish/authorize")
    assert r.status_code == 400 and "README" in r.json()["detail"]
