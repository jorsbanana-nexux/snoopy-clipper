"""
API Snoopy Clipper + server frontend statis.
Jalankan dari root project:  uvicorn backend.main:app --host 0.0.0.0 --port 8000
"""
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import config, pipeline, library, quota

# Job sisa sesi lama (server ter-kill/restart saat job jalan) tidak boleh
# nanggung "running" selamanya di UI — pulihkan begitu server hidup.
_recovered = pipeline.recover_stale_jobs()

app = FastAPI(title="Snoopy Clipper", version="1.1.0")


def require_key(request: Request):
    """Auth ringan tier-1: kosong API_KEY = mode lokal lama (semua bebas).
    Diisi = /api/clip, /api/jobs, /api/library wajib header X-API-Key (atau ?key=).
    Endpoint file (klip/thumbnail) tetap terbuka — id-nya acak & tak berisi data
    pribadi; begitu ada auth multi-user sungguhan, ganti ini."""
    if not config.API_KEY:
        return
    supplied = request.headers.get("X-API-Key") or request.query_params.get("key") or ""
    if supplied != config.API_KEY:
        raise HTTPException(401, "Kunci API salah — buka pengaturan dan tempel kuncinya.")


class ClipRequest(BaseModel):
    url: str


@app.get("/api/health")
def health():
    return {
        "ok": True,
        "gemini": bool(config.GEMINI_API_KEY),
        "whisper": f"{config.WHISPER_MODEL}/{config.WHISPER_COMPUTE}",
        "auth": bool(config.API_KEY),  # frontend minta kunci bila true
    }


@app.post("/api/clip")
def create_clip(req: ClipRequest, _=Depends(require_key)):
    url = req.url.strip()
    if not url.startswith(("http://", "https://")):
        raise HTTPException(400, "URL tidak valid — harus diawali http(s)://")
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
def get_quota(_=Depends(require_key)):
    """Kuota hari ini — dasar 'sisa kredit' di UI & fondasi billing."""
    return quota.usage()


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
