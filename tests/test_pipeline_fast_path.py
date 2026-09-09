"""Kontrak orkestrasi: caption-first panjang harus tetap benar-benar hemat."""
from backend import brain, captions, config, downloader, pipeline


def test_long_captioned_kids_video_skips_full_download(monkeypatch, tmp_path):
    """Video > ambang visual: otak menerima caption + mode Kids, bukan video penuh."""
    monkeypatch.setattr(config, "JOBS_DIR", tmp_path / "jobs")
    config.JOBS_DIR.mkdir()
    monkeypatch.setattr(config, "DOWNLOADS_DIR", tmp_path / "downloads")
    config.DOWNLOADS_DIR.mkdir()
    monkeypatch.setattr(config, "BRAIN_MULTIMODAL", True)
    monkeypatch.setattr(config, "BRAIN_FRAMES_MAX_DURATION", 240.0)
    monkeypatch.setattr(config, "CAPTIONS_FIRST", True)

    job_id = "captionedkids"
    pipeline._jobs[job_id] = {
        "id": job_id,
        "url": "https://www.youtube.com/watch?v=e_04ZrNroTo",
        "local_path": None,
        "kids_url": True,
        "status": "queued", "step": "queue", "message": "", "pct": 0,
        "eta_seconds": None, "clips": [], "error": None,
    }
    info = {"id": "child_source", "title": "Wheels on the Bus for Kids", "duration": 460.0,
            "uploader": "CoComelon"}
    observed = {}
    monkeypatch.setattr(downloader, "resolve_url", lambda url: ("video", {}, None))
    monkeypatch.setattr(downloader, "get_info", lambda url: info)
    monkeypatch.setattr(captions, "fetch", lambda url: {
        "language": "en", "lines": [{"start": 0, "end": 20, "text": "hello children"}], "words": [],
    })
    monkeypatch.setattr(pipeline, "_download_full", lambda *_: (_ for _ in ()).throw(
        AssertionError("caption-first video panjang tidak boleh download penuh")))
    monkeypatch.setattr(
        pipeline, "_render_ranged",
        lambda *args, **kwargs: observed.setdefault("rendered", args[2]),
    )

    def choose_moments(transcript, duration, frames_dir=None, frame_interval=None, meta=None):
        observed["frames"] = frames_dir
        observed["meta"] = meta
        return [{"start": 1.0, "end": 25.0, "title": "Aman", "score": 8}]

    monkeypatch.setattr(brain, "find_moments", choose_moments)
    try:
        pipeline._run(job_id)
        job = pipeline.get_job(job_id)
        assert job["status"] == "done"
        assert observed["frames"] is None
        assert observed["meta"]["is_kids"] is True
        assert observed["rendered"][0]["title"] == "Aman"
    finally:
        pipeline._jobs.pop(job_id, None)
