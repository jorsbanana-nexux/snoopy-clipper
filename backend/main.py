"""
API Snoopy Clipper + server frontend statis.
Jalankan dari root project:  uvicorn backend.main:app --host 0.0.0.0 --port 8000
"""
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import config, pipeline, library

app = FastAPI(title="Snoopy Clipper", version="1.0.0")


class ClipRequest(BaseModel):
    url: str


@app.get("/api/health")
def health():
    return {
        "ok": True,
        "gemini": bool(config.GEMINI_API_KEY),
        "whisper": f"{config.WHISPER_MODEL}/{config.WHISPER_COMPUTE}",
    }


@app.post("/api/clip")
def create_clip(req: ClipRequest):
    url = req.url.strip()
    if not url.startswith(("http://", "https://")):
        raise HTTPException(400, "URL tidak valid — harus diawali http(s)://")
    return {"job_id": pipeline.create_job(url)}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    job = pipeline.get_job(job_id)
    if not job:
        raise HTTPException(404, "Job tidak ditemukan")
    return job


@app.get("/api/library")
def get_library():
    return {"videos": library.list_videos()}


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
