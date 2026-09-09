"""
Orkestrator Snoopy Clipper — dua strategi, satu hasil.

JALUR CEPAT (default, CAPTIONS_FIRST=1, video dari URL):
  transkrip bawaan platform (instan, kilobytes) -> Gemini pilih momen ->
  unduh video HANYA rentang terpilih (download_ranges) ->
  whisper kecil per-klip (kata-per-kata untuk subtitle) -> render.
  Video 50 menit: yang diunduh & diproses hanya menit-menit terpilih.

JALUR KLASIK (fallback: platform tanpa transkrip / file lokal):
  audio-only -> whisper full -> Gemini -> unduh rentang / video penuh -> render.

Analisis visual (frame) tetap jalan untuk video <= BRAIN_FRAMES_MAX_DURATION.

Progress + ETA realtime dikoreksi otomatis dari kecepatan aktual (drift).
"""
import json
import queue
import threading
import time
import traceback
import uuid
from pathlib import Path

from . import (config, downloader, transcriber, brain, captions, diarize, thumbnail,
              facetrack, subtitles, cutter, library, bgm)

_jobs = {}
_lock = threading.Lock()
_queue: "queue.Queue[str]" = queue.Queue()
_worker_started = None


# ---------------- infrastruktur job ----------------

def _persist(job):
    """Tulis status job secara atomik.

    Frontend dapat mem-poll kapan saja. Menulis langsung ke file JSON membuat
    pembaca sesekali menerima JSON setengah jadi ketika update progres terjadi.
    Tulis ke file sementara lalu replace agar setiap pembaca melihat snapshot
    lengkap lama atau lengkap baru, tidak pernah data korup.
    """
    path = config.JOBS_DIR / f"{job['id']}.json"
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(job, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def _worker():
    while True:
        job_id = _queue.get()
        try:
            _run(job_id)
        except Exception:
            traceback.print_exc()
        finally:
            _queue.task_done()


def _ensure_worker():
    global _worker_started
    if _worker_started is None:
        threading.Thread(target=_worker, daemon=True).start()
        _worker_started = True


def create_job(url: str, local_path: str = None) -> str:
    """Mulai job. Berikan `url`, ATAU `local_path` untuk file yang sudah ada di disk."""
    orig_url = (url or "").strip()
    kids_url = "youtubekids." in orig_url.lower()  # sinyal kids sebelum dinormalisasi
    url = downloader.normalize_url(orig_url)
    job_id = uuid.uuid4().hex[:12]
    job = {
        "id": job_id, "url": url or f"local:{local_path}", "local_path": local_path,
        "kids_url": kids_url,
        "status": "queued", "step": "queue",
        "message": "Menunggu antrean…", "pct": 0, "eta_seconds": None,
        "clips": [], "error": None, "created": time.time(),
    }
    with _lock:
        _jobs[job_id] = job
        _persist(job)
    _ensure_worker()
    _queue.put(job_id)
    return job_id


def get_job(job_id: str):
    with _lock:
        job = _jobs.get(job_id)
        if job:
            return dict(job)
    p = config.JOBS_DIR / f"{job_id}.json"  # job lama (misal server restart)
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return None


def _update(job_id, **kw):
    with _lock:
        job = _jobs[job_id]
        job.update(kw)
        _persist(job)


def _drift(elapsed: float, estimated: float) -> float:
    """Rasio kecepatan aktual vs estimasi. Di-clamp biar ETA tidak gila."""
    if not estimated or estimated <= 0:
        return 1.0
    return min(3.0, max(0.3, elapsed / estimated))


# ---------------- estimasi waktu ----------------

def _estimates(duration: float) -> dict:
    """Jalur klasik (whisper full) — estimasi per langkah untuk PC low-spec CPU."""
    est = {
        "download": max(15.0, duration / 6.0),
        "audio": 6.0,
        "transcribe": max(25.0, duration * 0.55),
    }
    if config.BRAIN_MULTIMODAL:
        est["frames"] = max(10.0, duration * 0.08)
        est["brain"] = 30.0
    else:
        est["brain"] = 18.0
    return est


def _step_order() -> list:
    order = ["download", "audio", "transcribe"]
    if config.BRAIN_MULTIMODAL:
        order.append("frames")
    order.append("brain")
    return order


def _left(est: dict, from_step: str, drift: float, render_est_left: float) -> float:
    order = _step_order()
    remaining = sum(est[k] for k in order[order.index(from_step):])
    return remaining * drift + render_est_left


# ---------------- pipeline utama ----------------

def _run(job_id):
    job = _jobs[job_id]
    try:
        _update(job_id, status="running", step="info",
                message="Mengambil info video…", pct=2, eta_seconds=None)
        local = job.get("local_path")
        if local:
            info = downloader.get_info_local(local)
        else:
            # URL bisa berupa video, CHANNEL/PROFILE, atau playlist (semua
            # platform) — channel otomatis diseleksi: pilih video TERBAIK
            # (diperhitungkan dari popularitas & kesesuaian klip, bukan random)
            kind, ch, entries = downloader.resolve_url(job["url"])
            if kind == "channel":
                _update(job_id, step="info", pct=3,
                        message=f"Channel terdeteksi: {ch['title']} — memilih video "
                                f"terbaik dari {len(entries)} kandidat "
                                f"(diperhitungkan, bukan random)…")
                vurl, vtitle, why = downloader.pick_channel_best(entries)
                if not vurl:
                    raise RuntimeError(f"Channel ini {why}.")
                job["url"] = vurl
                _update(job_id, pct=4,
                        message=f"Dipilih: {vtitle} — {why}. Lanjut proses normal…")
            info = downloader.get_info(job["url"])
        duration = info["duration"]
        _jobs[job_id]["info"] = info  # konteks utk otak v3 (judul/channel/deteksi anak)
        if duration <= 0:
            raise RuntimeError("Durasi video tidak terbaca — coba URL lain.")
        _update(job_id, video=info, pct=5,
                message=f"Video: {info['title']} ({int(duration // 60)}m {int(duration % 60)}d)")

        # ===== A. FILE LOKAL: jalur klasik penuh =====
        if local:
            transcript = _transcribe_full(job_id, info, Path(local), duration)
            frames = _frames(job_id, Path(local), info, duration)
            moments = _brain(job_id, transcript, duration, frames)
            _render_absolute(job_id, info, moments, Path(local), transcript["words"])
            return _finish(job_id, info)

        # ===== B. URL: coba transkrip instan (jalur cepat) =====
        caps = None
        if config.CAPTIONS_FIRST:
            _update(job_id, step="captions", pct=8,
                    message="Mengambil transkrip bawaan platform…")
            caps = captions.fetch(job["url"])
            if caps:
                _update(job_id, pct=15,
                        message=f"Transkrip platform siap: {len(caps['lines'])} baris "
                                f"(bahasa {caps['language']}) — whisper full-video DILEWATI")
            else:
                _update(job_id, pct=10,
                        message="Platform tanpa transkrip — pakai jalur klasik (whisper)")

        use_frames = config.BRAIN_MULTIMODAL and duration <= config.BRAIN_FRAMES_MAX_DURATION

        if caps:
            if use_frames:
                # video pendek: unduh penuh (sekalian bahan render) + analisis visual
                video_path = _download_full(job_id, info)
                frames = _frames(job_id, video_path, info, duration)
                moments = _brain(job_id, caps, duration, frames)
                _render_absolute(job_id, info, moments, video_path, full_words=None)
            else:
                # video panjang: TANPA unduh full — otak dulu, lalu unduh hanya rentang
                moments = _brain(job_id, caps, duration, None)
                _render_ranged(job_id, info, moments, full_words=None)
        else:
            if use_frames:
                video_path = _download_full(job_id, info)
                transcript = _transcribe_full(job_id, info, video_path, duration)
                frames = _frames(job_id, video_path, info, duration)
                moments = _brain(job_id, transcript, duration, frames)
                _render_absolute(job_id, info, moments, video_path,
                                 full_words=transcript["words"])
            else:
                # fallback panjang tanpa transkrip: audio-only -> whisper -> unduh rentang
                transcript = _transcribe_audio_only(job_id, info, duration)
                moments = _brain(job_id, transcript, duration, None)
                _render_ranged(job_id, info, moments, full_words=transcript["words"])

        _finish(job_id, info)
    except Exception as e:
        traceback.print_exc()
        _update(job_id, status="error", message=f"Gagal: {e}", error=str(e))


# ---------------- langkah-langkah ----------------

def _download_full(job_id, info) -> Path:
    """Unduh video penuh (cache: video sama tidak diunduh ulang)."""
    est = _estimates(float(info.get("duration") or 0))
    _update(job_id, step="download", message="Mengunduh video…", pct=10,
            eta_seconds=_left(est, "download", 1.0, 0.0))
    out_base = config.DOWNLOADS_DIR / info["id"]
    # yt-dlp biasanya merge menjadi MP4, tetapi extractor tertentu sah-sah saja
    # mengembalikan WebM/MKV. Jangan mengasumsikan ekstensi .mp4 untuk cache.
    video_path = downloader.cached_media(out_base)
    if video_path is None:
        video_path = Path(downloader.download(_jobs[job_id]["url"], out_base))
    _update(job_id, pct=15, message="Video siap")
    return Path(video_path)


def _frames(job_id, video_path, info, duration):
    """Cuplikan frame untuk analisis visual otak (cache per video)."""
    est = _estimates(duration)
    _update(job_id, step="frames", pct=45,
            message="Menyiapkan cuplikan frame untuk analisis visual…",
            eta_seconds=_left(est, "frames", 1.0, 0.0))
    frames_dir = config.DOWNLOADS_DIR / f"{info['id']}_frames"
    interval = cutter.extract_frames(video_path, frames_dir, duration)
    return (frames_dir, interval)


def _transcribe_full(job_id, info, video_path, duration) -> dict:
    """Jalur klasik: whisper dari audio video (penuh)."""
    est = max(25.0, duration * 0.55)
    wav_path = config.DOWNLOADS_DIR / f"{info['id']}.wav"
    _update(job_id, step="audio", message="Menyiapkan audio…", pct=20)
    if not wav_path.exists():
        cutter.extract_audio(video_path, wav_path)

    def prog(frac):
        _update(job_id, pct=25 + int(19 * frac),
                message=f"Transkripsi Whisper {config.WHISPER_MODEL}: {int(frac * 100)}% — berjalan normal, bukan stuck",
                eta_seconds=max(5.0, est_left - est * frac))

    est_left = _left(_estimates(duration), "transcribe", 1.0, 0.0)
    _update(job_id, step="transcribe", pct=25,
            message=f"Transkripsi Whisper {config.WHISPER_MODEL} {config.WHISPER_COMPUTE}…",
            eta_seconds=est_left)
    t0 = time.time()
    transcript = transcriber.transcribe(wav_path, expected_duration=duration, on_progress=prog)
    if not transcript["words"]:
        raise RuntimeError("Tidak ada ucapan terdeteksi — otak AI butuh transkrip untuk memilih momen.")
    transcript = diarize.maybe_diarize(
        transcript, wav_path,
        on_progress=lambda f, m: _update(job_id, step="diarize", pct=45 + int(3 * f), message=m))
    _update(job_id, pct=45,
            message=f"Transkrip ok: {len(transcript['lines'])} baris, bahasa {transcript['language']} "
                    f"({int(time.time() - t0)} dtk)")
    return transcript


def _transcribe_audio_only(job_id, info, duration) -> dict:
    """Fallback video panjang tanpa transkrip platform: unduh AUDIO saja (ringan)."""
    _update(job_id, step="audio", pct=12,
            message="Mengunduh audio saja (tanpa video penuh)…")
    got = None
    for ext in (".m4a", ".opus", ".webm", ".mp3"):
        cand = config.DOWNLOADS_DIR / f"{info['id']}_audio{ext}"
        if cand.exists():
            got = cand
            break
    if got is None:
        got = Path(downloader.download_audio(_jobs[job_id]["url"],
                                             config.DOWNLOADS_DIR / f"{info['id']}_audio"))
    wav_path = config.DOWNLOADS_DIR / f"{info['id']}.wav"
    if not wav_path.exists():
        cutter.extract_audio(got, wav_path)
    est = max(25.0, duration * 0.55)

    def prog(frac):
        _update(job_id, pct=20 + int(24 * frac),
                message=f"Transkripsi Whisper {config.WHISPER_MODEL}: {int(frac * 100)}% — berjalan normal, bukan stuck",
                eta_seconds=max(5.0, est * (1 - frac)))

    _update(job_id, step="transcribe", pct=20,
            message=f"Transkripsi Whisper {config.WHISPER_MODEL} (audio)…", eta_seconds=est)
    t0 = time.time()
    transcript = transcriber.transcribe(wav_path, expected_duration=duration, on_progress=prog)
    if not transcript["words"]:
        raise RuntimeError("Tidak ada ucapan terdeteksi — otak AI butuh transkrip untuk memilih momen.")
    transcript = diarize.maybe_diarize(
        transcript, wav_path,
        on_progress=lambda f, m: _update(job_id, step="diarize", pct=45 + int(3 * f), message=m))
    _update(job_id, pct=45,
            message=f"Transkrip ok: {len(transcript['lines'])} baris, bahasa {transcript['language']} "
                    f"({int(time.time() - t0)} dtk)")
    return transcript


def _brain(job_id, transcript, duration, frames) -> list:
    frames_dir, frame_interval = frames if frames else (None, None)
    _update(job_id, step="brain", pct=48,
            message="Gemini menganalisis momen terbaik"
                    + (" (transkrip + visual)…" if frames_dir else " (transkrip lengkap)…"),
            eta_seconds=_estimates(duration)["brain"])
    t0 = time.time()
    # KONTEKS v3: judul + channel + deteksi anak -> otak pahami dulu, baru pilih
    job = _jobs[job_id]
    info = job.get("info") or {}
    meta = {
        "title": info.get("title", ""),
        "uploader": info.get("uploader", ""),
        "is_kids": bool(job.get("kids_url")) or downloader.detect_kids(
            job["url"], info.get("title", ""), info.get("uploader", "")),
    }
    if meta["is_kids"]:
        _update(job_id, message="Mode video anak terdeteksi — otak memilih momen ramah keluarga")
    moments = brain.find_moments(transcript, duration, frames_dir, frame_interval, meta=meta)
    if not moments:
        raise RuntimeError("AI tidak menemukan momen yang layak jadi klip. Coba video lain.")
    _update(job_id, pct=50, message=f"{len(moments)} momen terpilih — mulai render "
            f"(otak {int(time.time() - t0)} dtk)")
    return moments


# ---------------- kata-per-kata klip ----------------

def _clip_words(job_id, info, m, i, full_words, seg_path=None, absolute_shift=None,
                on_progress=None, clip_dur=None):
    """
    Kata-per-kata satu klip (untuk subtitle MrBeast).
    Prioritas: slice dari whisper full (kalau ada, gratis), else whisper segmen kecil.
    - mode ABSOLUTE (video penuh): kembalikan kata ber-waktu ABSOLUT sumber.
    - mode LOKAL (segmen unduhan rentang): kembalikan kata ber-waktu LOKAL (0-based).
    absolute_shift = m['start'] untuk menggeser hasil whisper segmen -> absolut.
    """
    if full_words:
        words = [w for w in full_words
                 if w["end"] > m["start"] + 0.2 and w["start"] < m["end"] - 0.2]
        if words:
            return words
    wav_path = config.DOWNLOADS_DIR / f"{info['id']}_c-s{m['start']:.2f}-e{m['end']:.2f}.wav"
    if not wav_path.exists():
        if seg_path is not None:
            # segmen rentang: audio sudah sekecil klipnya
            cutter.extract_audio(seg_path, wav_path)
        else:
            # dari video penuh: potong hanya rentang klip (kecil, cepat)
            cutter.extract_audio(config.DOWNLOADS_DIR / f"{info['id']}.mp4", wav_path,
                                 time_range=(m["start"], m["end"]))
    transcript = transcriber.transcribe(
        wav_path, expected_duration=clip_dur, on_progress=on_progress)
    words = transcript["words"]  # waktu LOKAL rentang
    if absolute_shift is not None:
        words = [{"start": w["start"] + absolute_shift, "end": w["end"] + absolute_shift,
                  "text": w["text"]} for w in words]
    return words


# ---------------- render ----------------

def _render_absolute(job_id, info, moments, video_path, full_words):
    """Render dari video PENUH dengan seek absolut (-ss). Dipakai utk video pendek
    & file lokal. Timeline subtitle absolut (clip_start = awal klip)."""
    src_w, src_h = facetrack.get_dims(video_path)
    cw, ch = cutter.crop_size(src_w, src_h)
    tw, th = cutter.pick_target(src_w, src_h)
    workdir = config.JOBS_DIR / f"{job_id}_tmp"
    workdir.mkdir(parents=True, exist_ok=True)
    vdir = library.video_dir(info["id"])
    total = len(moments)
    render_factor = 2.2 if config.GAME_ULTRA else 1.6
    render_est = [(m["end"] - m["start"]) * render_factor + 6.0 for m in moments]
    meta_clips = []
    for i, m in enumerate(moments):
        base_pct = 50 + int(45 * i / total)
        span = max(1, int(45 / total))
        try:  # tahan gagal per-klip: satu klip error tidak boleh merobek semuanya
            _update(job_id, step="render", pct=base_pct,
                    message=f"Klip {i + 1}/{total}: {m['title']}",
                    eta_seconds=sum(render_est[i:]))
            start, end = m["start"], m["end"]
            _update(job_id, step="render", pct=base_pct + int(span * 0.2),
                    message=f"Klip {i + 1}/{total}: {m['title']} — subtitle kata-per-kata…")

            def word_prog(frac, i=i, base_pct=base_pct, span=span, m=m, total=total):
                _update(job_id, pct=min(99, base_pct + int(span * (0.2 + 0.35 * frac))),
                        message=f"Klip {i + 1}/{total}: {m['title']} — subtitle {int(frac * 100)}%")

            words = _clip_words(job_id, info, m, i, full_words,
                                absolute_shift=None if full_words else start,
                                on_progress=word_prog, clip_dur=end - start)
            # fase senyap diberi pesan agar UI tidak tampak 'diam'
            _update(job_id, step="render", pct=base_pct + int(span * 0.55),
                    message=f"Klip {i + 1}/{total}: {m['title']} — analisis wajah & kamera…")
            times = []
            t = max(0.0, start - 0.5)
            while t <= end + 0.5:
                times.append(round(t, 2))
                t += config.FACE_SAMPLE_INTERVAL
            # t0=start: keyframe digeser ke waktu LOKAL (ffmpeg -ss reset t ke 0)
            # word_spans (Whisper): gerak mulut dihitung 'bicara' hanya saat ada
            # ucapan nyata — orang yang ketawa/nyengir saat jeda tak mencuri kamera
            spans = [(w["start"], w["end"]) for w in words] if words else None
            keyframes, focus_y, vision = facetrack.track(video_path, times, src_w, cw,
                                                         t0=start, word_spans=spans)
            clip_id = f"clip_{i + 1:02d}"
            ass_file = workdir / f"{clip_id}.ass"
            ass_file.write_text(
                subtitles.build_ass(words, focus_y, vision, tw, th, start, end),
                encoding="utf-8")
            out_path = vdir / f"{clip_id}.mp4"
            t0 = time.time()

            _update(job_id, step="render", pct=base_pct + int(span * 0.9),
                    message=f"Klip {i + 1}/{total}: {m['title']} — render…",
                    eta_seconds=sum(render_est[i:]))

            def on_progress(p, i=i, base_pct=base_pct, span=span, rsum=sum(render_est[i:])):
                _update(job_id, pct=min(99, base_pct + int(span * (0.9 + 0.1 * p))),
                        eta_seconds=max(3.0, rsum * (1 - p)))

            bgm_track = _bgm_track(job_id, m) if config.BGM else None
            cutter.render_clip(video_path, start, end, ass_file.name, keyframes,
                               src_w, src_h, out_path, workdir, on_progress=on_progress,
                               bgm=bgm_track)
            _enforce_full_audio(job_id, i + 1, total, out_path)
            if config.THUMBNAIL:
                thumbnail.make_thumb(video_path, start, end, out_path, vdir / f"{clip_id}.jpg")
            # DRIFT KALIBRASI: kecepatan nyata klip ini melatih estimasi klip
            # berikutnya — ETA makin akurat sepanjang job (bukan tebakan statis)
            drift = _drift(time.time() - t0, render_est[i])
            for j in range(i + 1, total):
                render_est[j] = max(5.0, render_est[j] * drift)
            meta_clips.append(_clip_meta(clip_id, m, tw, th, info,
                                         (bgm_track or {}).get("credit", "")))
        except Exception as e:
            traceback.print_exc()
            _update(job_id, message=f"Klip {i + 1}/{total} ({m['title']}) gagal: {e} — "
                                    f"lanjut ke klip berikutnya…")
            continue
    if not meta_clips:
        raise RuntimeError("Semua klip gagal dirender — cek log server & coba lagi.")
    if len(meta_clips) < total:
        _update(job_id, message=f"Selesai: {len(meta_clips)}/{total} klip berhasil "
                                f"(yang gagal dilewati — klip sukses tetap tersimpan)")
    _save(job_id, info, meta_clips)


def _render_ranged(job_id, info, moments, full_words):
    """Jalur super-hemat video panjang: unduh HANYA rentang tiap klip
    (download_ranges), semua proses di timeline segmen (lokal).
    Platform tanpa dukungan rentang -> fallback video penuh (absolute)."""
    url = _jobs[job_id]["url"]
    total = len(moments)
    render_factor = 2.2 if config.GAME_ULTRA else 1.6
    dl_est = [max(8.0, (m["end"] - m["start"]) / 6.0 + 4) for m in moments]
    wh_est = [(m["end"] - m["start"]) * 0.55 + 3 for m in moments]
    rd_est = [(m["end"] - m["start"]) * render_factor + 6.0 for m in moments]

    # Tes dukungan rentang dengan klip pertama (fallback rapi kalau tidak didukung).
    # Jangan mengasumsikan hasilnya .mp4; beberapa extractor mengembalikan WebM
    # atau MKV walau merge_output_format telah diminta.
    m0 = moments[0]
    seg0_base = _seg_base(info, m0)
    seg0 = downloader.cached_media(seg0_base)
    if seg0 is None:
        _update(job_id, step="render", pct=50,
                message=f"Klip 1/{total}: {m0['title']} — unduh rentang…",
                eta_seconds=sum(dl_est) + sum(wh_est) + sum(rd_est))
        try:
            def dl0(frac, m0=m0, total=total):
                _update(job_id, step="render", pct=50 + int(3 * frac),
                        message=f"Klip 1/{total}: {m0['title']} — unduh rentang {int(frac * 100)}%")
            seg0 = Path(downloader.download(url, seg0_base,
                                             time_range=(m0["start"], m0["end"]), on_progress=dl0))
        except Exception:
            _update(job_id, message="Rentang tidak didukung platform — unduh video penuh…")
            video_path = _download_full(job_id, info)
            return _render_absolute(job_id, info, moments, video_path, full_words)

    workdir = config.JOBS_DIR / f"{job_id}_tmp"
    workdir.mkdir(parents=True, exist_ok=True)
    vdir = library.video_dir(info["id"])
    meta_clips = []
    for i, m in enumerate(moments):
        base_pct = 50 + int(45 * i / total)
        span = max(1, int(45 / total))
        try:  # tahan gagal per-klip: satu klip error tidak boleh merobek semuanya
            seg_base = _seg_base(info, m)
            seg_path = downloader.cached_media(seg_base)
            if seg_path is None:
                _update(job_id, step="render", pct=base_pct,
                        message=f"Klip {i + 1}/{total}: {m['title']} — unduh rentang "
                                f"{int(m['start'])}-{int(m['end'])}d…",
                        eta_seconds=sum(dl_est[i:]) + sum(wh_est[i:]) + sum(rd_est[i:]))
                t0 = time.time()

                def dl_prog(frac, i=i, m=m, base_pct=base_pct, span=span, total=total):
                    _update(job_id, step="render",
                            pct=base_pct + int(span * (0.05 + 0.2 * frac)),
                            message=f"Klip {i + 1}/{total}: {m['title']} — unduh rentang {int(frac * 100)}%")

                seg_path = Path(downloader.download(
                    url, seg_base, time_range=(m["start"], m["end"]), on_progress=dl_prog))
            seg_dur = cutter.probe_duration(seg_path)
            if seg_dur <= 0.5:
                raise RuntimeError(f"Segmen klip {i + 1} gagal (durasi {seg_dur:.1f}s)")
            src_w, src_h = facetrack.get_dims(seg_path)
            cw, ch = cutter.crop_size(src_w, src_h)
            tw, th = cutter.pick_target(src_w, src_h)

            # kata-per-kata di timeline lokal: slice whisper full (digeser) atau whisper segmen
            _update(job_id, step="render", pct=base_pct + int(span * 0.25),
                    message=f"Klip {i + 1}/{total}: {m['title']} — subtitle kata-per-kata…")

            def word_prog(frac, i=i, base_pct=base_pct, span=span, m=m, total=total):
                _update(job_id, pct=min(99, base_pct + int(span * (0.25 + 0.35 * frac))),
                        message=f"Klip {i + 1}/{total}: {m['title']} — subtitle {int(frac * 100)}%")

            words = _clip_words_local(info, m, i, seg_path, full_words,
                                      on_progress=word_prog, seg_dur=seg_dur)
            # face tracking di timeline SEGMEN (lokal) — sadar ucapan (Whisper):
            # mulut bergerak saat JEDA = ketawa/nyengir, bukan pembicara
            _update(job_id, step="render", pct=base_pct + int(span * 0.6),
                    message=f"Klip {i + 1}/{total}: {m['title']} — analisis wajah & kamera…")
            times = []
            t = 0.0
            while t <= seg_dur + 0.5:
                times.append(round(t, 2))
                t += config.FACE_SAMPLE_INTERVAL
            spans = [(w["start"], w["end"]) for w in words] if words else None
            keyframes, focus_y, vision = facetrack.track(seg_path, times, src_w, cw,
                                                          t0=0.0, word_spans=spans)
            clip_id = f"clip_{i + 1:02d}"
            ass_file = workdir / f"{clip_id}.ass"
            ass_file.write_text(
                subtitles.build_ass(words, focus_y, vision, tw, th, 0.0, seg_dur),
                encoding="utf-8")
            out_path = vdir / f"{clip_id}.mp4"
            t0 = time.time()  # untuk kalibrasi drift klip berikutnya
            _update(job_id, step="render", pct=base_pct + int(span * 0.9),
                    message=f"Klip {i + 1}/{total}: {m['title']} — render…",
                    eta_seconds=sum(rd_est[i:]))

            def on_progress(p, i=i, base_pct=base_pct, span=span, rsum=sum(rd_est[i:])):
                _update(job_id, pct=min(99, base_pct + int(span * (0.9 + 0.1 * p))),
                        eta_seconds=max(3.0, rsum * (1 - p)))

            bgm_track = _bgm_track(job_id, m) if config.BGM else None
            cutter.render_clip(seg_path, 0.0, seg_dur, ass_file.name, keyframes,
                               src_w, src_h, out_path, workdir, on_progress=on_progress,
                               bgm=bgm_track)
            _enforce_full_audio(job_id, i + 1, total, out_path)
            if config.THUMBNAIL:
                thumbnail.make_thumb(seg_path, 0.0, seg_dur, out_path, vdir / f"{clip_id}.jpg")
            # DRIFT KALIBRASI (ranged): kecepatan nyata -> estimasi klip berikut
            drift = _drift(time.time() - t0, rd_est[i])
            for j in range(i + 1, total):
                rd_est[j] = max(5.0, rd_est[j] * drift)
            meta_clips.append(_clip_meta(clip_id, m, tw, th, info,
                                         (bgm_track or {}).get("credit", "")))
        except Exception as e:
            traceback.print_exc()
            _update(job_id, message=f"Klip {i + 1}/{total} ({m['title']}) gagal: {e} — "
                                    f"lanjut ke klip berikutnya…")
            continue
    if not meta_clips:
        raise RuntimeError("Semua klip gagal dirender — cek log server & coba lagi.")
    if len(meta_clips) < total:
        _update(job_id, message=f"Selesai: {len(meta_clips)}/{total} klip berhasil "
                                f"(yang gagal dilewati — klip sukses tetap tersimpan)")
    _save(job_id, info, meta_clips)


def _clip_words_local(info, m, i, seg_path, full_words,
                     on_progress=None, seg_dur=None):
    """Kata-per-kata di timeline LOKAL segmen: slice whisper full (digeser turun)
    atau whisper segmen kecil (menit-an saja, bukan video penuh)."""
    if full_words:
        words = [{"start": w["start"] - m["start"], "end": w["end"] - m["start"],
                  "text": w["text"]}
                 for w in full_words
                 if w["end"] > m["start"] + 0.2 and w["start"] < m["end"] - 0.2]
        if words:
            return words
    wav_path = Path(seg_path).with_suffix(".wav")  # ikut nama segmen (di-key rentang)
    if not wav_path.exists():
        cutter.extract_audio(seg_path, wav_path)
    return transcriber.transcribe(
        wav_path, expected_duration=seg_dur, on_progress=on_progress)["words"]


def _enforce_full_audio(job_id, n_clip, total, out_path):
    """AUDIO WAJIB FULL — bukan sekadar peringatan (keputusan owner):
    apad sudah menjamin di filter graph; cek ini gerbang terakhir.
    Kalau audio tetap kurang panjang: PERBAIKI otomatis (pad ke panjang
    video, video stream-copy). Kalau masih gagal -> raise agar klip
    ditandai gagal & TIDAK TERSIMPAN — video sunyi tak pernah delivery."""
    warn = cutter.av_duration_check(out_path)
    if not warn:
        return
    _update(job_id, message=f"Klip {n_clip}/{total}: {warn} — perbaiki otomatis…")
    if not cutter.repair_audio_tail(out_path):
        raise RuntimeError(f"{warn} — perbaikan otomatis gagal, klip dilewati "
                            f"(jangan sampai tersimpan video sunyi)")
    warn2 = cutter.av_duration_check(out_path)
    if warn2:
        raise RuntimeError(f"{warn2} — tetap bermasalah setelah perbaikan, klip dilewati")
    _update(job_id, message=f"Klip {n_clip}/{total}: audio diperbaiki — kini full "
                            f"sepanjang video ✓")


def _seg_base(info, m) -> Path:
    """Nama file segmen di-key RENTANG WAKTU (bukan nomor klip) — aman untuk
    re-run: otak boleh memilih momen berbeda di run berikutnya tanpa
    memakai segmen lama yang basi (bug: klip lama tampil momen yang salah)."""
    # key tanpa titik (dengan_suffix aman): perpuluahan detik -> integer
    k0, k1 = int(round(m["start"] * 10)), int(round(m["end"] * 10))
    return config.DOWNLOADS_DIR / f"{info['id']}_s{k0:05d}-e{k1:05d}"


def _bgm_track(job_id, m):
    """BGM utk satu klip: mood dari otak -> track lokal (unduh SEKALI lalu cache).
    Tidak pernah boleh menggagalkan render: error apapun -> klip tetap jalan
    tanpa BGM (pesan di UI), bukan gagal total."""
    try:
        title = bgm.pick(m.get("bgm_mood"), _jobs[job_id].get("bgm_used", []))
        if not bgm.track_path(title).exists():
            _update(job_id, message=f"BGM: mengunduh '{title}' sekali saja "
                                    f"(cache permanen, klip berikutnya instan)…")
            bgm.ensure_track(title)
        used = _jobs[job_id].setdefault("bgm_used", [])
        if title not in used:
            used.append(title)
        return {"path": str(bgm.track_path(title)), "volume": config.BGM_VOLUME,
                "credit": bgm.credit(title)}
    except Exception:
        traceback.print_exc()
        _update(job_id, message="BGM dilewati (gagal menyiapkan) — render lanjut tanpa bgm…")
        return None


# ---------------- meta & selesai ----------------

def _clip_meta(clip_id, m, tw, th, info, bgm_credit="") -> dict:
    return {
        "id": clip_id, "title": m["title"], "hook": m.get("hook", ""),
        "score": m.get("score", 0), "reason": m.get("reason", ""),
        "trend": m.get("trend", ""), "audience": m.get("audience", ""),
        "bgm": bgm_credit,
        "start": m["start"], "end": m["end"],
        "duration": round(m["end"] - m["start"], 1),
        "width": tw, "height": th,
        "path": f"/api/clips/{info['id']}/{clip_id}",
        "thumb": f"/api/thumbs/{info['id']}/{clip_id}",
    }


def _save(job_id, info, meta_clips):
    library.save_meta({
        "id": info["id"], "title": info["title"], "url": _jobs[job_id]["url"],
        "uploader": info["uploader"], "created": time.time(), "clips": meta_clips,
    })
    _update(job_id, clips=meta_clips)


def _finish(job_id, info):
    clips = _jobs[job_id].get("clips", [])
    workdir = config.JOBS_DIR / f"{job_id}_tmp"
    if workdir.exists():
        for f in workdir.iterdir():
            f.unlink()
        workdir.rmdir()
    _update(job_id, status="done", step="done", pct=100, eta_seconds=0,
            message=f"Selesai! {len(clips)} klip siap diunduh.", video_id=info["id"])
