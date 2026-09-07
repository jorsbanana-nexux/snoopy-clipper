"""
Render klip final — SATU PASS ffmpeg: crop pintur 9:16 + MOTION BLUR ala game +
burn subtitle + scale + encode.
Motion blur hanya aktif saat kamera pan (kecepatan pan diketahui dari keyframe),
blend halus dengan frame sebelumnya — penonton lihat gerakan sinematik, bukan smear.
Auto-detect encoder GPU (NVENC) kalau ada; kalau tidak, x264 preset hemat CPU.
Seek akurat frame-level (-ss sebelum -i) supaya potongan pas: tak lebih, tak kurang.
"""
import os
import subprocess
import time

from . import config

_encoder = None


def pick_encoder():
    """-> (list_arg_encoder, nama_untuk_info). GPU kalau ada, CPU kalau tidak."""
    global _encoder
    if _encoder:
        return _encoder
    try:
        r = subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi",
             "-i", "color=c=black:s=256x256:d=0.1", "-c:v", "h264_nvenc",
             "-f", "null", "-"],
            capture_output=True, timeout=30,
        )
        if r.returncode == 0:
            _encoder = (["-c:v", "h264_nvenc", "-rc", "vbr", "-cq", "23"], "GPU NVENC")
            return _encoder
    except Exception:
        pass
    _encoder = (
        ["-c:v", "libx264", "-preset", config.X264_PRESET, "-crf", config.X264_CRF],
        f"CPU x264 {config.X264_PRESET}",
    )
    return _encoder


def pick_target(src_w: int, src_h: int):
    """1080x1920 kalau sumber cukup; kalau tidak, 720x1280. Bisa dipaksa via FORCE_RESOLUTION."""
    forced = config.FORCE_RESOLUTION
    if forced == "1080":
        return 1080, 1920
    if forced == "720":
        return 720, 1280
    return (1080, 1920) if src_h >= 1080 else (720, 1280)


def crop_size(src_w: int, src_h: int):
    """Ukuran crop 9:16 dari frame sumber (wajah di-track horizontal)."""
    if src_w >= src_h * 9 / 16:  # landscape / square -> potong kiri-kanan
        ch = src_h
        cw = int(src_h * 9 / 16) // 2 * 2
    else:  # portrait -> potong atas-bawah
        cw = (src_w // 2) * 2
        ch = min(src_h, int(cw * 16 / 9))
    return cw, ch


def _x_expr(keyframes: list, crop_w: int, src_w: int) -> str:
    """Ekspresi ffmpeg untuk pan horizontal: interpolasi linear antar keyframe.
    Kecepatan kontinu by construction (path dibangun offline dengan clamp kecepatan)."""
    lo, hi = crop_w // 2, src_w - crop_w // 2
    pts = [(t, min(max(x, lo), hi) - crop_w // 2) for t, x in keyframes]
    if not pts:
        return str((src_w - crop_w) // 2)
    if len(pts) == 1:
        return str(int(pts[0][1]))
    expr = f"{int(pts[-1][1])}"
    for i in range(len(pts) - 2, -1, -1):
        t0, x0 = pts[i]
        t1, x1 = pts[i + 1]
        frac = f"max(0,min(1,(t-{t0:.2f})/({t1 - t0:.2f})))"
        expr = f"if(lt(t,{t1:.2f}),{int(x0)}+({int(x1) - int(x0)})*({frac}),{expr})"
    return expr


def _crop_filter(src_w, src_h, keyframes) -> str:
    cw, ch = crop_size(src_w, src_h)
    y = (src_h - ch) // 2
    if src_w > cw + 2:  # ada ruang pan horizontal -> ikuti wajah
        return f"crop={cw}:{ch}:x='{_x_expr(keyframes, cw, src_w)}':y={y}"
    return f"crop={cw}:{ch}:x=0:y={y}"


def _motion_blur_filter(keyframes: list, src_w: int) -> str:
    """
    MOTION BLUR ala game: aktif HANYA di rentang waktu kamera pan cepat.
    Kecepatan pan diketahui dari keyframe (offline) -> enable expression presisi.
    Blend 'strength frame sebelumnya + 1 frame kini' (dinormalisasi otomatis ffmpeg).
    """
    if not config.MOTION_BLUR or len(keyframes) < 2:
        return None
    v_thresh = src_w * 0.03  # px/detik — drift lambat tidak di-blur
    segs = []
    for i in range(len(keyframes) - 1):
        t0, x0 = keyframes[i]
        t1, x1 = keyframes[i + 1]
        v = abs(x1 - x0) / max(t1 - t0, 1e-6)
        if v > v_thresh:
            s, e = t0 - 0.15, t1 + 0.15  # padding halus masuk/keluar blur
            if segs and s <= segs[-1][1]:
                segs[-1] = (segs[-1][0], e)
            else:
                segs.append((s, e))
    if not segs:
        return None
    enable = "+".join(f"between(t,{s:.2f},{e:.2f})" for s, e in segs)
    w = config.MOTION_BLUR_STRENGTH
    return f"tmix=frames=2:weights='{w} 1':enable='{enable}'"


def _grade_filter() -> list:
    """
    GRADE "GAME ULTRA" — semua filter murah, tetap dalam SATU pass:
    1. eq: kontras naik + gamma turun sedikit -> bayangan pekat & tajam
       (imitasi "Shadow Quality Ultra"), plus saturasi biar warna hidup.
    2. hue: rotasi kecil ke arah hangat -> kulit manusia tampak lebih hidup
       dan kemerahan saat kena cahaya (imitasi "subsurface scattering").
    3. unsharp: ketajaman tekstur (imitasi "Texture Quality Ultra"),
       HANYA luma (chroma=0) supaya tidak memunculkan noise warna.
    """
    # Dipilih dari BENCHMARK biaya CPU (murah -> mahal):
    # eq ~4%, hue ~5%, unsharp 3x3 ~62% — jauh lebih hemat daripada
    # colorbalance (~303%) / lutrgb (~77%) / unsharp 5x5 (~113%).
    if not config.GAME_ULTRA:
        return []
    parts = []
    if config.EQ_CONTRAST != 1.0 or config.EQ_GAMMA != 1.0 or config.EQ_SATURATION != 1.0:
        parts.append(
            "eq=contrast=%.3f:gamma=%.3f:saturation=%.3f"
            % (config.EQ_CONTRAST, config.EQ_GAMMA, config.EQ_SATURATION)
        )
    if config.WARM_HUE_DEG != 0.0:
        parts.append("hue=h=%.1f" % config.WARM_HUE_DEG)
    if config.UNSHARP_AMOUNT > 0:
        parts.append("unsharp=3:3:%.2f:3:3:0.0" % config.UNSHARP_AMOUNT)
    return parts


def extract_audio(video_path, wav_path, time_range=None):
    """Wav 16kHz mono (makanan whisper). time_range=(s,e) detik: potong hanya rentang itu."""
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error"]
    if time_range:
        cmd += ["-ss", f"{time_range[0]:.3f}", "-t", f"{time_range[1] - time_range[0]:.3f}"]
    cmd += ["-i", str(video_path), "-vn", "-ac", "1", "-ar", "16000",
            "-c:a", "pcm_s16le", str(wav_path)]
    subprocess.run(cmd, check=True)


def probe_duration(path) -> float:
    """Durasi media (detik) via ffprobe."""
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(path)],
        capture_output=True, text=True,
    ).stdout.strip()
    try:
        return float(out)
    except ValueError:
        return 0.0



def extract_frames(video_path, out_dir, duration: float) -> float:
    """
    Cuplikan frame untuk OTAK MULTIMODAL (dilihat Gemini) — kecil & hemat.
    Interval menyesuaikan supaya total frame <= config.BRAIN_MAX_FRAMES.
    -> interval (frame ke-i ada di detik i*interval). Cache per video.
    """
    import math
    from pathlib import Path
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    existing = sorted(out_dir.glob("f_*.jpg"))
    if existing:
        # interval tersimpan via jumlah file + durasi file cache
        return max(config.BRAIN_FRAME_INTERVAL,
                   duration / max(config.BRAIN_MAX_FRAMES, 1))
    interval = max(config.BRAIN_FRAME_INTERVAL,
                   duration / max(config.BRAIN_MAX_FRAMES, 1))
    subprocess.run(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(video_path),
         "-vf", f"fps=1/{interval:.2f},scale=320:-2",
         "-frames:v", str(config.BRAIN_MAX_FRAMES + 2),
         str(out_dir / "f_%03d.jpg")],
        check=True,
    )
    return interval


def render_clip(video_path, start, end, ass_rel_path, keyframes, src_w, src_h,
                out_path, workdir, on_progress=None):
    """
    Render satu klip (satu pass): crop pintar + motion blur + subtitle burn + encode.
    Motion blur diaplikasikan SEBELUM subtitle supaya teks selalu tajam.
    on_progress(frac 0..1) dipanggil berkala untuk update ETA.
    -> (tw, th, nama_encoder)
    """
    tw, th = pick_target(src_w, src_h)
    enc, enc_name = pick_encoder()
    clip_dur = end - start
    video_path = os.path.abspath(video_path)  # aman walau cwd = workdir
    out_path = os.path.abspath(out_path)

    parts = [_crop_filter(src_w, src_h, keyframes), f"scale={tw}:{th}:flags=lanczos"]
    parts.extend(_grade_filter())  # grade dulu, blur & subtitle tetap di atasnya
    mb = _motion_blur_filter(keyframes, src_w)
    if mb:
        parts.append(mb)
    if ass_rel_path:
        parts.append(f"ass='{ass_rel_path}'")
    vf = ",".join(parts)

    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-nostats", "-loglevel", "error",
        "-ss", f"{start:.3f}", "-i", str(video_path), "-t", f"{clip_dur:.3f}",
        "-vf", vf, *enc,
        "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart",
        "-progress", "pipe:1", str(out_path),
    ]
    proc = subprocess.Popen(cmd, cwd=str(workdir), stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True)
    last = 0.0
    for line in proc.stdout:
        line = line.strip()
        if line.startswith("out_time_ms=") and on_progress:
            try:
                done = int(line.split("=", 1)[1]) / 1e6  # out_time_ms = mikrodetik
            except ValueError:
                continue
            now = time.time()
            if now - last >= 0.7:
                last = now
                on_progress(min(0.999, done / clip_dur))
    proc.wait()
    err = proc.stderr.read() if proc.stderr else ""
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg gagal: {err[-800:]}")
    return tw, th, enc_name
