"""
API Snoopy Clipper + server frontend statis.
Jalankan dari root project:  uvicorn backend.main:app --host 0.0.0.0 --port 8000
"""
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import json
import secrets
import time
import urllib.parse
import urllib.request

from . import config, pipeline, library, quota, publisher, accounts, billing

from fastapi.responses import HTMLResponse, RedirectResponse

# Job sisa sesi lama (server ter-kill/restart saat job jalan) tidak boleh
# nanggung "running" selamanya di UI — pulihkan begitu server hidup.
_recovered = pipeline.recover_stale_jobs()

app = FastAPI(title="Snoopy Clipper", version="1.1.0")


def require_key(request: Request):
    """Auth ringan tier-1: kosong API_KEY = mode lokal lama (semua bebas).
    Diisi = /api/clip, /api/jobs, /api/library wajib header X-API-Key (atau ?key=).
    Endpoint file (klip/thumbnail) tetap terbuka — id-nya acak & tak berisi data
    pribadi; begitu ada auth multi-user sungguhan, ganti ini."""
    if config.MULTIUSER:
        # gap #6: kunci API per-user (accounts.py). API_KEY global diabaikan.
        supplied = (request.headers.get("X-API-Key")
                    or request.query_params.get("key") or "")
        user = accounts.get_by_key(supplied)
        if not user:
            raise HTTPException(401, "Kunci API tidak dikenal — login dulu.")
        request.state.user = user
        return user
    if not config.API_KEY:
        return
    supplied = request.headers.get("X-API-Key") or request.query_params.get("key") or ""
    if supplied != config.API_KEY:
        raise HTTPException(401, "Kunci API salah — buka pengaturan dan tempel kuncinya.")


class ClipRequest(BaseModel):
    url: str = ""
    local_path: str = ""


@app.get("/api/health")
def health():
    return {
        "ok": True,
        "gemini": bool(config.GEMINI_API_KEY),
        "whisper": f"{config.WHISPER_MODEL}/{config.WHISPER_COMPUTE}",
        "auth": bool(config.API_KEY),  # frontend minta kunci bila true
        "multiuser": bool(config.MULTIUSER),  # frontend tampil login/daftar bila true
    }


@app.post("/api/clip")
def create_clip(req: ClipRequest, user=Depends(require_key)):
    url = req.url.strip()
    local = req.local_path.strip()
    if local:
        if not Path(local).is_file():
            raise HTTPException(400, f"File lokal tidak ditemukan: {local}")
        return {"job_id": pipeline.create_job(local_path=local)}
    if not url.startswith(("http://", "https://")):
        raise HTTPException(400, "URL tidak valid — harus diawali http(s)://, "
                                 "atau kirim local_path untuk file lokal")
    if config.MULTIUSER and user:
        # kuota & penagihan melekat pada akun yang memesan, bukan global
        return {"job_id": pipeline.create_job(
            url, user_key=user["api_key"],
            plan_minutes=accounts.plan_minutes(user))}
    return {"job_id": pipeline.create_job(url)}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str, _=Depends(require_key)):
    job = pipeline.get_job(job_id)
    if not job:
        raise HTTPException(404, "Job tidak ditemukan")
    return job


@app.get("/api/library")
def get_library(_=Depends(require_key)):
    return {"videos": library.list_videos()}


@app.get("/api/quota")
def get_quota(user=Depends(require_key)):
    """Kuota hari ini — dasar 'sisa kredit' di UI & fondasi billing.
    Mode multi-user: kuota milik akun pemanggil (bukan global)."""
    if config.MULTIUSER and user:
        return quota.user_usage(user["api_key"], accounts.plan_minutes(user))
    return quota.usage()


# ===================== MULTI-USER & BILLING (gap #6) =====================
class AuthRequest(BaseModel):
    email: str
    password: str


class CheckoutRequest(BaseModel):
    plan: str = "pro"
    days: int = 30


class GrantRequest(BaseModel):
    email: str
    plan: str
    days: int = 30


def _multiuser_guard():
    if not config.MULTIUSER:
        raise HTTPException(403, "Server mode lokal (MULTIUSER=0) — tanpa akun.")


@app.post("/api/auth/register")
def auth_register(req: AuthRequest):
    """Buat akun -> dapat kunci API pribadi + plan Free. Password disimpan
    sebagai PBKDF2 (lihat accounts.py)."""
    _multiuser_guard()
    try:
        user = accounts.register(req.email, req.password)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"email": user["email"], "api_key": user["api_key"], "plan": "free"}


@app.post("/api/auth/login")
def auth_login(req: AuthRequest):
    _multiuser_guard()
    user = accounts.login(req.email, req.password)
    if not user:
        existing = accounts.get(req.email)
        if existing and not existing.get("pwhash"):
            raise HTTPException(400, "Akun ini dibuat via Google — "
                                     "pakai tombol Masuk dengan Google.")
        raise HTTPException(401, "Email atau password salah.")
    return {"email": user["email"], "api_key": user["api_key"],
            "plan": accounts.effective_plan(user)}


@app.get("/api/me")
def me(user=Depends(require_key)):
    _multiuser_guard()
    return {**accounts.public(user),
            "quota": quota.user_usage(user["api_key"], accounts.plan_minutes(user))}


@app.get("/api/billing/plans")
def billing_plans(user=Depends(require_key)):
    return {
        "plans": {k: {"label": v["label"], "daily_minutes": v["daily_minutes"]}
                 for k, v in accounts.PLANS.items()},
        "pro_price_idr": config.PLAN_PRO_PRICE_IDR,
        "gateway": billing.gateway(),  # "midtrans" | "manual"
    }


@app.post("/api/billing/checkout")
def billing_checkout(req: CheckoutRequest, user=Depends(require_key)):
    """Midtrans terpasang -> URL pembayaran; jika tidak -> mode manual
    (transfer bank, admin grant). Jualan bisa jalan tanpa gateway."""
    _multiuser_guard()
    try:
        order = billing.create_order(user, req.plan, req.days)
    except ValueError as e:
        raise HTTPException(400, str(e))
    resp = {"order_id": order["order_id"], "amount_idr": order["amount_idr"],
            "status": order["status"], "payment_url": order["payment_url"]}
    if order["status"] == "awaiting_manual":
        resp["manual_instructions"] = (
            "Transfer Rp" + f"{order['amount_idr']:,}".replace(",", ".")
            + " ke rekening admin, lalu kirim bukti + kode order "
            + order["order_id"] + f" — admin akan mengaktifkan plan {req.plan} "
            f"{req.days} hari setelah pembayaran diverifikasi.")
    return resp


@app.post("/api/billing/midtrans-webhook")
def midtrans_webhook(payload: dict):
    """Dipanggil server Midtrans (server-ke-server), tanpa kunci —
    keamanan lewat signature SHA-512; tanpa signature valid -> 403."""
    try:
        billing.handle_notification(payload)
    except ValueError:
        raise HTTPException(403, "Notifikasi tidak valid.")
    return {"ok": True}


@app.post("/api/billing/grant")
def billing_grant(req: GrantRequest, user=Depends(require_key)):
    """Admin mengaktifkan plan manual (jualan transfer-bank / retensi)."""
    if not (config.MULTIUSER and accounts.is_admin(user)):
        raise HTTPException(403, "Hanya admin.")
    try:
        target = accounts.grant(req.email, req.plan, req.days)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return accounts.public(target)

# ---------------- Login dengan Google (gap #6, opsional) ----------------
# Memakai OAuth client YouTube yang sudah terpasang (YT_CLIENT_ID/SECRET)
# atau client sendiri via GOOGLE_LOGIN_CLIENT_ID. Scope BUKAN youtube:
# openid + email + profile saja (Google tidak perlu setujui app untuk ini
# bila dipakai personal; app "testing" + akun tester sendiri sudah cukup).
_GOOGLE_AUTH = "https://accounts.google.com/o/oauth2/v2/auth"
_GOOGLE_TOKEN = "https://oauth2.googleapis.com/token"
_GOOGLE_TOKENINFO = "https://oauth2.googleapis.com/tokeninfo"
_google_states: dict = {}  # state -> epoch (anti-CSRF, TTL 10 menit)


def _google_creds():
    return (config.GOOGLE_LOGIN_CLIENT_ID or config.YT_CLIENT_ID,
            config.GOOGLE_LOGIN_CLIENT_SECRET or config.YT_CLIENT_SECRET)


def _gredirect(request: Request) -> str:
    return str(request.base_url).rstrip("/") + "/api/auth/google/callback"


@app.get("/api/auth/google/url")
def google_login_url(request: Request):
    _multiuser_guard()
    cid, _ = _google_creds()
    if not cid:
        raise HTTPException(503, "Login Google belum dikonfigurasi — isi "
                                 "YT_CLIENT_ID atau GOOGLE_LOGIN_CLIENT_ID.")
    now = time.time()
    for k in [k for k, v in _google_states.items() if now - v > 600]:
        _google_states.pop(k, None)
    state = secrets.token_hex(16)
    _google_states[state] = now
    q = urllib.parse.urlencode({
        "client_id": cid, "redirect_uri": _gredirect(request),
        "response_type": "code", "scope": "openid email profile",
        "state": state, "prompt": "select_account"})
    return {"url": _GOOGLE_AUTH + "?" + q}


@app.get("/api/auth/google/callback")
def google_login_callback(request: Request, code: str = "",
                          state: str = "", error: str = ""):
    """Balik dari Google: tukar code -> id_token, verifikasi lewat endpoint
    resmi Google (signature, audiens, email_verified), lalu login/daftar
    otomatis. Kunci API ditanam ke localStorage lewat HTML satu-baris
    (asal sama dengan frontend, aman)."""
    if error:
        return HTMLResponse(
            "<script>alert('Login Google dibatalkan.');location.href='/'</script>")
    issued = _google_states.pop(state, None)
    if not issued or time.time() - issued > 600:
        return HTMLResponse(
            "<script>alert('Sesi login Google kedaluwarsa — coba lagi.');"
            "location.href='/'</script>", status_code=400)
    cid, csec = _google_creds()
    body = urllib.parse.urlencode({
        "code": code, "client_id": cid, "client_secret": csec,
        "redirect_uri": _gredirect(request),
        "grant_type": "authorization_code"}).encode()
    with urllib.request.urlopen(urllib.request.Request(
            _GOOGLE_TOKEN, data=body, method="POST"), timeout=20) as r:
        tok = json.loads(r.read())
    if not tok.get("id_token"):
        raise HTTPException(400, "Google tidak mengirim id_token.")
    with urllib.request.urlopen(_GOOGLE_TOKENINFO + "?id_token="
            + urllib.parse.quote(tok["id_token"]), timeout=20) as r:
        info = json.loads(r.read())
    if (info.get("aud") != cid
            or str(info.get("email_verified")).lower() != "true"
            or not info.get("email")):
        raise HTTPException(400, "Token Google tidak valid.")
    user = accounts.upsert_google(info["email"])
    return HTMLResponse(
        "<script>localStorage.setItem('snoopy_key','" + user["api_key"]
        + "');location.href='/';</script>")


@app.get("/api/stats")
def get_stats(_=Depends(require_key)):
    """Statistik instan dari file job (tanpa DB): laporan status & kecepatan."""
    import json as _json
    import time as _time
    done, error, running, queued, secs, clips = 0, 0, 0, 0, 0.0, 0
    for p in config.JOBS_DIR.glob("*.json"):
        try:
            j = _json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        st = j.get("status")
        if st == "done":
            done += 1
            clips += len(j.get("clips") or [])
            c, u = j.get("created"), j.get("updated")
            if isinstance(c, (int, float)) and isinstance(u, (int, float)):
                secs += max(0.0, u - c)
        elif st == "error":
            error += 1
        elif st == "running":
            running += 1
        elif st == "queued":
            queued += 1
    return {
        "jobs_done": done, "jobs_error": error,
        "jobs_running": running, "jobs_queued": queued,
        "clips_total": clips,
        "avg_seconds_per_job": (round(secs / done, 1) if done else None),
        "quota": quota.usage(),
        "ts": _time.time(),
    }


# ---------------- AUTO-POST YouTube Shorts ----------------

@app.get("/api/publish/authorize")
def publish_authorize(_=Depends(require_key)):
    """Buka URL ini di browser -> setujui akses YouTube -> token tersimpan."""
    if not publisher.configured():
        raise HTTPException(400, "YT_CLIENT_ID/SECRET belum diisi di .env (lihat README publish).")
    return {"url": publisher.authorize_url()}


@app.get("/api/publish/callback")
def publish_callback(code: str = "", error: str = ""):
    """Google mengarah kembali ke sini. Tidak pakai kunci — code sekali-pakai."""
    if error or not code:
        return HTMLResponse(
            "<h3>Izin YouTube ditolak/batal.</h3><p>reload Snoopy dan coba lagi.</p>",
            status_code=400)
    try:
        publisher.exchange_code(code)
    except Exception as e:
        return HTMLResponse(f"<h3>Gagal menukar kode izin.</h3><p>{e}</p>", status_code=400)
    return RedirectResponse("/", status_code=302)  # kembali ke UI, token sudah tersimpan


class PublishRequest(BaseModel):
    title: str = ""
    description: str = ""


@app.post("/api/publish/{video_id}/{clip_id}")
def publish_clip(video_id: str, clip_id: str, req: PublishRequest,
                 _=Depends(require_key)):
    """Unggah klip ke channel sebagai Shorts; balas URL video."""
    p = library.clip_path(video_id, clip_id)
    if not p.exists():
        raise HTTPException(404, "Klip tidak ditemukan")
    try:
        clip = next((c for c in library.load_meta(video_id).get("clips", [])
                     if c.get("id") == clip_id), {})
    except Exception:
        clip = {}
    title = (req.title or clip.get("title") or p.stem).strip()
    desc = req.description or (clip.get("hook") or "")
    try:
        url = publisher.upload_clip(p, title, desc)
    except Exception as e:
        raise HTTPException(502, f"Upload gagal: {e}")
    return {"url": url, "title": title}


@app.get("/api/thumbs/{video_id}/{clip_id}")
def get_thumb(video_id: str, clip_id: str):
    """Thumbnail klip (SELALU ada — dijamin modul thumbnail)."""
    from . import library, config
    p = config.LIBRARY_DIR / video_id / f"{clip_id}.jpg"
    if not p.exists():
        library.video_dir(video_id)
        from . import thumbnail
        thumbnail.make_thumb(p, 0, 0, p, p)  # regenerasi placeholder — tak pernah 404
    return FileResponse(p, media_type="image/jpeg")


@app.get("/api/clips/{video_id}/{clip_id}")
def get_clip(video_id: str, clip_id: str):
    p = library.clip_path(video_id, clip_id)
    if not p.exists():
        raise HTTPException(404, "Klip tidak ditemukan")
    return FileResponse(p, media_type="video/mp4", filename=f"{clip_id}.mp4")


# frontend statis (vanilla — tanpa build step)
app.mount("/", StaticFiles(directory=str(config.FRONTEND_DIR), html=True), name="frontend")
