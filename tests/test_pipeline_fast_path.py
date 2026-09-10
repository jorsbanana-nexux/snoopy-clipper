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
    monkeypatch.setattr(config, "BRAIN_FRAMES_PROXY", False)
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


def test_long_captioned_video_gets_frames_proxy(monkeypatch, tmp_path):
    """Proxy visual hemat: video panjang kini DILIHAT otak, tanpa download penuh."""
    monkeypatch.setattr(config, "JOBS_DIR", tmp_path / "jobs")
    config.JOBS_DIR.mkdir()
    monkeypatch.setattr(config, "DOWNLOADS_DIR", tmp_path / "downloads")
    config.DOWNLOADS_DIR.mkdir()
    monkeypatch.setattr(config, "BRAIN_MULTIMODAL", True)
    monkeypatch.setattr(config, "BRAIN_FRAMES_MAX_DURATION", 240.0)
    monkeypatch.setattr(config, "BRAIN_FRAMES_PROXY", True)
    monkeypatch.setattr(config, "CAPTIONS_FIRST", True)

    job_id = "proxylong"
    pipeline._jobs[job_id] = {
        "id": job_id, "url": "https://www.youtube.com/watch?v=longvideo",
        "local_path": None, "kids_url": False,
        "status": "queued", "step": "queue", "message": "", "pct": 0,
        "eta_seconds": None, "clips": [], "error": None,
    }
    info = {"id": "long_src", "title": "Podcast Panjang", "duration": 3000.0, "uploader": "Ch"}
    observed = {}
    monkeypatch.setattr(downloader, "resolve_url", lambda url: ("video", {}, None))
    monkeypatch.setattr(downloader, "get_info", lambda url: info)
    monkeypatch.setattr(captions, "fetch", lambda url: {
        "language": "en", "lines": [{"start": 0, "end": 20, "text": "hello"}], "words": [],
    })
    monkeypatch.setattr(pipeline, "_download_full", lambda *_: (_ for _ in ()).throw(
        AssertionError("proxy tidak boleh memicu download penuh")))
    monkeypatch.setattr(
        pipeline, "_render_ranged",
        lambda *args, **kwargs: observed.setdefault("rendered", args[2]),
    )

    def fake_proxy(jid, inf, dur):
        observed["proxy_called"] = True
        return (tmp_path / "frames", 62.5)

    monkeypatch.setattr(pipeline, "_frames_proxy", fake_proxy)

    def choose_moments(transcript, duration, frames_dir=None, frame_interval=None, meta=None):
        observed["frames"] = frames_dir
        observed["interval"] = frame_interval
        return [{"start": 1.0, "end": 25.0, "title": "Terlihat", "score": 8}]

    monkeypatch.setattr(brain, "find_moments", choose_moments)
    try:
        pipeline._run(job_id)
        job = pipeline.get_job(job_id)
        assert job["status"] == "done"
        assert observed["proxy_called"] is True
        assert observed["frames"] == tmp_path / "frames"
        assert observed["interval"] == 62.5
    finally:
        pipeline._jobs.pop(job_id, None)


def test_frames_proxy_failure_is_soft(monkeypatch, tmp_path):
    """Proxy mati -> otak lanjut dari teks; job TIDAK boleh gagal karenanya."""
    monkeypatch.setattr(config, "DOWNLOADS_DIR", tmp_path / "downloads")
    config.DOWNLOADS_DIR.mkdir()
    info = {"id": "soft_src", "title": "X", "duration": 3000.0, "uploader": "Ch"}
    pipeline._jobs["softjob"] = {"id": "softjob", "url": "u"}

    def boom(*a, **k):
        raise RuntimeError("proxy server down")

    monkeypatch.setattr(downloader, "cached_media", lambda base: None)
    monkeypatch.setattr(downloader, "download_frames_proxy", boom)
    try:
        result = pipeline._frames_proxy("softjob", info, 3000.0)
        assert result is None
    finally:
        pipeline._jobs.pop("softjob", None)
