"""Auto-post klip ke YouTube (Shorts) — Google OAuth + resumable upload.
STDLIB SAJA (urllib) — tanpa dependency baru, Dockerfile tidak berubah.

Alur pemakaian:
  1. GET  /api/publish/authorize        -> URL izin Google (1x per akun)
  2. Google redirect ke /api/publish/callback?code=... -> token disimpan ke file
  3. POST /api/publish/{vid}/{cid}     -> unggah klip sebagai Shorts, balas URL

TikTok/IG menyusul: TikTok Content Posting API butuh audit app (mingguan),
IG Graph API butuh akun business + review — YouTube dulu karena instan.
"""
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

from . import config

_TOKEN_PATH = Path(config.YT_TOKEN_FILE) if config.YT_TOKEN_FILE else config.JOBS_DIR / "yt_token.json"
_AUTH = "https://accounts.google.com/o/oauth2/v2/auth"
_TOKEN_URL = "https://oauth2.googleapis.com/token"
_UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos"


def configured() -> bool:
    return bool(config.YT_CLIENT_ID and config.YT_CLIENT_SECRET)


def authorized() -> bool:
    return configured() and _TOKEN_PATH.exists()


def authorize_url() -> str:
    """URL izin Google — user tinggal buka & setujui. Scope MINIM: upload saja."""
    q = urllib.parse.urlencode({
        "client_id": config.YT_CLIENT_ID,
        "redirect_uri": config.YT_REDIRECT_URI,
        "response_type": "code",
        "scope": "https://www.googleapis.com/auth/youtube.upload",
        "access_type": "offline",   # minta refresh token (long-lived)
        "prompt": "consent",         # wajib agar refresh token selalu dikirim
    })
    return f"{_AUTH}?{q}"


def _http_json(url: str, data: dict) -> dict:
    req = urllib.request.Request(url, data=urllib.parse.urlencode(data).encode(),
                                 method="POST",
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def exchange_code(code: str):
    """Code sekali-pakai -> token akses + refresh token (disimpan ke file)."""
    tok = _http_json(_TOKEN_URL, {
        "client_id": config.YT_CLIENT_ID,
        "client_secret": config.YT_CLIENT_SECRET,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": config.YT_REDIRECT_URI,
    })
    if "refresh_token" not in tok:
        raise RuntimeError(
            "Google tidak mengirim refresh token — buka ulang URL izin dan pastikan "
            "prompt=consent dipakai (atau hapus akses app di myaccount.google.com dulu).")
    _save_token(tok)


def _save_token(tok: dict):
    tok["saved_at"] = time.time()
    _TOKEN_PATH.write_text(json.dumps(tok), encoding="utf-8")


def access_token() -> str:
    """Token akses segar — refresh otomatis kalau sudah lewat (cache 60 detik)."""
    tok = json.loads(_TOKEN_PATH.read_text(encoding="utf-8"))
    exp = tok.get("saved_at", 0) + int(tok.get("expires_in", 3599)) - 60
    if time.time() >= exp:
        fresh = _http_json(_TOKEN_URL, {
            "client_id": config.YT_CLIENT_ID,
            "client_secret": config.YT_CLIENT_SECRET,
            "refresh_token": tok["refresh_token"],
            "grant_type": "refresh_token",
        })
        tok.update(fresh)
        _save_token(tok)
    return tok["access_token"]


def upload_clip(path: Path, title: str, description: str = "") -> str:
    """Unggah MP4 ke channel sebagai Shorts (resumable). Balas URL video."""
    if not configured():
        raise RuntimeError("YT_CLIENT_ID/SECRET belum diisi di .env — lihat README bagian publish.")
    if not authorized():
        raise RuntimeError("Belum izinkan akses YouTube — buka /api/publish/authorize dulu.")
    size = path.stat().st_size
    meta = {
        "snippet": {"title": title[:95], "description": (description or "")[:4900],
                    "categoryId": "22"},
        "status": {"privacyStatus": config.PUBLISH_PRIVACY,
                   "selfDeclaredMadeForKids": False},
    }
    token = access_token()
    # Tahap 1: sesi resumable -> Location
    req = urllib.request.Request(
        f"{_UPLOAD_URL}?uploadType=resumable&part=snippet,status",
        data=json.dumps(meta).encode(), method="POST",
        headers={"Authorization": f"Bearer {token}",
                 "Content-Type": "application/json; charset=UTF-8",
                 "X-Upload-Content-Type": "video/mp4",
                 "X-Upload-Content-Length": str(size)})
    with urllib.request.urlopen(req, timeout=60) as r:
        loc = r.headers.get("Location")
    if not loc:
        raise RuntimeError("Google tidak memberi URL unggahan (Location kosong).")
    # Tahap 2: kirim bytes ke Location
    req = urllib.request.Request(loc, data=path.read_bytes(), method="PUT",
                                headers={"Content-Type": "video/mp4"})
    with urllib.request.urlopen(req, timeout=600) as r:
        out = json.loads(r.read().decode())
    return f"https://youtu.be/{out['id']}"
