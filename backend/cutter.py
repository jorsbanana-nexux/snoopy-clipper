"""
Render klip final — SATU PASS ffmpeg: crop pintur 9:16 + MOTION BLUR ala game +
burn subtitle + scale + encode.
Motion blur hanya aktif saat kamera pan (kecepatan pan diketahui dari keyframe),
blend halus dengan frame sebelumnya — penonton lihat gerakan sinematik, bukan smear.
Auto-detect encoder GPU (NVENC) kalau ada; kalau tidak, x264 preset hemat CPU.
Seek akurat frame-level (-ss sebelum -i) supaya potongan pas: tak lebih, tak kurang.
"""
import json
import os
import subprocess
import time
from pathlib import Path

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
    """Ekspresi ffmpeg untuk pan horizontal: interpolasi KUBIK Catmull-Rom antar
    keyframe -> kecepatan kontinu (C1) di tiap titik — pan terasa mulus, bukan
    'macet skala kecil' seperti interpolasi linear (kecepatan melompat di tiap
    keyframe). Posisi sub-pixel (float, tanpa pembulatan int kasar).
    Biaya runtime: nihil (hanya string ekspresi lebih panjang, di-evaluasi
    per-frame sama seperti sebelumnya)."""
    lo, hi = crop_w / 2, src_w - crop_w / 2
    pts = [(t, min(max(x, lo), hi) - crop_w / 2) for t, x in keyframes]
    if not pts:
        return str((src_w - crop_w) // 2)
    if len(pts) == 1:
        return f"{pts[0][1]:.2f}"
    if len(pts) == 2:
        # hanya 2 titik: linear (terjadi pada pan pendek statis) — tetap float
        (t0, x0), (t1, x1) = pts
        frac = f"max(0,min(1,(t-{t0:.2f})/({t1 - t0:.2f})))"
        return f"{x0:.2f}+({x1 - x0:.2f})*({frac})"

    def seg_expr(i: int) -> str:
        # kubik Catmull-Rom segmen pts[i] -> pts[i+1]; endpoint di-duplicate
        (t0, x0), (t1, x1) = pts[i], pts[i + 1]
        p0 = pts[i - 1][1] if i - 1 >= 0 else x0
        p3 = pts[i + 2][1] if i + 2 < len(pts) else x1
        a1 = 0.5 * (x1 - p0)
        a2 = 0.5 * (2 * p0 - 5 * x0 + 4 * x1 - p3)
        a3 = 0.5 * (3 * x0 - p0 - 3 * x1 + p3)
        dt = max(t1 - t0, 0.01)
        u = f"max(0,min(1,(t-{t0:.2f})/{dt:.2f}))"
        return (f"{x0:.2f}+({a1:.4f})*{u}+({a2:.4f})*{u}*{u}"
                f"+({a3:.4f})*{u}*{u}*{u}")

    expr = f"{pts[-1][1]:.2f}"
    for i in range(len(pts) - 2, -1, -1):
        t1 = pts[i + 1][0]
        expr = f"if(lt(t,{t1:.2f}),{seg_expr(i)},{expr})"
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


def av_duration_check(out_path):
    """Sanity A/V output: audio wajib >= durasi video (apad menjamin ini).
    Return pesan peringatan kalau mencurigakan, None kalau sehat.
    Alat diagnostik murah (<50ms) — masalah 'suara hilang' bisa terdeteksi
    sejak render, bukan menunggu dilihat penonton."""
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,duration",
             "-of", "json", str(out_path)],
            capture_output=True, text=True, timeout=30)
        dur = {}
        for st in json.loads(r.stdout or "{}").get("streams", []):
            dur[st.get("codec_type")] = float(st.get("duration") or 0)
        va, vv = dur.get("audio", 0.0), dur.get("video", 0.0)
        if vv > 0 and va > 0 and va < vv - 0.5:
            return f"peringatan A/V: audio {va:.1f}s < video {vv:.1f}s (cek sumber)"
    except Exception:
        pass
    return None


def repair_audio_tail(out_path) -> bool:
    """PERBAIKI otomatis output yang audionya lebih pendek dari video:
    pad audio ke panjang video (apad + -shortest). Video stream-copy —
    cepat, tanpa render ulang. True kalau sukses."""
    tmp = Path(str(out_path) + ".fix.mp4")
    try:
        r = subprocess.run(
            ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
             "-i", str(out_path), "-map", "0:v:0", "-map", "0:a:0",
             "-c:v", "copy", "-af", "apad", "-shortest",
             "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart",
             str(tmp)],
            capture_output=True, text=True, timeout=600)
        if r.returncode != 0 or not tmp.exists() or tmp.stat().st_size < 1000:
            tmp.unlink(missing_ok=True)
            return False
        tmp.replace(out_path)
        return True
    except Exception:
        tmp.unlink(missing_ok=True)
        return False


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


def _voice_chain() -> str:
    """Daging audio: suara manusia diperlakukan ala studio — highpass buang
    gemuruh, denoise desis ringan, kompresi rapat, loudness -14 LUFS
    (standar platform: YT/TikTok/IG). VOICE_TREAT=0 = polos (perilaku lama)."""
    if not config.VOICE_TREAT:
        return ""
    return ("highpass=f=80,afftdn=nr=12:nf=-28,"
            "acompressor=threshold=-18dB:ratio=2.5:attack=8:release=120,"
            "loudnorm=I=-14:TP=-1.5:LRA=11")


def render_clip(video_path, start, end, ass_rel_path, keyframes, src_w, src_h,
                out_path, workdir, on_progress=None, bgm=None, loop=False,
                wm_rel_path=None, hook_rel_path=None, hook_dur=2.6):
    """
    Render satu klip (satu pass): crop pintar + motion blur + grade + subtitle
    burn + WATERMARK (kiri-atas) + HOOK overlay (awal klip) + VOICE TREATMENT
    (-14 LUFS) + BGM mix + encode. Semua fitur daging opsional (None/flag .env).
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

    voice = _voice_chain()
    a_pad = (voice + ",apad") if voice else "apad"

    # ---- overlay PNG: watermark (kiri-atas, sepanjang klip) + hook (awal) ----
    overlays = []
    if wm_rel_path:
        overlays.append((wm_rel_path, "main_w*0.035", "main_h*0.025", None, True))
    if hook_rel_path:
        hd = max(0.4, min(hook_dur, clip_dur * 0.9))
        # APNG animasi (fade+blur): main SEKALI saja — jangan -loop 1,
        # frame terakhir transparan jadi eof pun tak meninggalkan apa pun.
        overlays.append((hook_rel_path, "(main_w-overlay_w)/2", "main_h*0.085",
                         f"between(t,0.15,{hd:.2f})", False))

    if bgm or overlays:
        base = 2 if bgm else 1
        chains = [f"[0:v]{vf}[v0]"]
        last = "v0"
        for k, (png, ox, oy, enable, oloop) in enumerate(overlays):
            nxt = f"vo{k}"
            e = f":enable='{enable}'" if enable else ""
            chains.append(f"[{last}][{base + k}:v]overlay=x='{ox}':y='{oy}'{e}[{nxt}]")
            last = nxt
        if bgm:  # BGM: satu pass yang sama, volume rendah + fade
            vol = float(bgm.get("volume", 0.15))
            if loop:
                # Klip LOOP ALAMI: fade BGM pendek-suprapat supaya jahitan loop
                # nyaris tak terasa — penonton memutar ulang tanpa sadar.
                fin = min(0.35, clip_dur / 8)
                fout_d = min(0.35, clip_dur / 8)
            else:
                fin = min(0.8, clip_dur / 4)
                fout_d = min(1.2, clip_dur / 4)
            # apad: suara sumber bisa LEBIH PENDEK dari video (padding keyframe)
            # -> tanpa ini audio & BGM mati mendadak di ekor klip.
            chains.append(f"[0:a]{a_pad}[a0]")
            chains.append(
                f"[1:a]atrim=0:{clip_dur:.3f},asetpts=PTS-STARTPTS,"
                f"volume={vol:.3f},"
                f"afade=t=in:st=0:d={fin:.3f},"
                f"afade=t=out:st={max(0.0, clip_dur - fout_d):.3f}:d={fout_d:.3f}[bgm]")
            chains.append("[a0][bgm]amix=inputs=2:duration=longest:"
                          "dropout_transition=0:normalize=0[aout]")
        else:
            chains.append(f"[0:a]{a_pad}[aout]")
        cmd = ["ffmpeg", "-y", "-hide_banner", "-nostats", "-loglevel", "error",
               "-ss", f"{start:.3f}", "-i", str(video_path), "-t", f"{clip_dur:.3f}"]
        if bgm:
            cmd += ["-stream_loop", "-1", "-i", str(bgm["path"])]
        for png, _, _, _, oloop in overlays:
            # PNG statis (watermark) -> -loop 1; APNG animasi (hook) -> sekali
            cmd += (["-loop", "1"] if oloop else []) + ["-i", png]
        cmd += ["-filter_complex", ";".join(chains),
                "-map", f"[{last}]", "-map", "[aout]", *enc,
                "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart",
                # WAJIB: batasi durasi OUTPUT (input loop/pad tak terbatas)
                "-t", f"{clip_dur:.3f}",
                "-progress", "pipe:1", str(out_path)]
    else:
        cmd = [
            "ffmpeg", "-y", "-hide_banner", "-nostats", "-loglevel", "error",
            "-ss", f"{start:.3f}", "-i", str(video_path), "-t", f"{clip_dur:.3f}",
            "-vf", vf, *enc,
            "-af", a_pad,  # voice treatment + audio selalu sepanjang video
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


def mix_bgm_pass(in_path, bgm, loop=False, clip_dur=None,
                 sfx_times=None, hook_pop=False):
    """Pass audio SETELAH render/concat (video stream-copy, nyaris nol
    biaya CPU): campur BGM (fade utuh satu kali) + SFX whoosh di tiap
    titik sfx_times (timeline final, detik) + pop lembut saat hook muncul.
    bgm boleh None (SFX saja). Tak ada yang bisa dicampur -> no-op."""
    from . import sfx as _sfx
    in_path = os.path.abspath(in_path)
    if not clip_dur or clip_dur <= 0:
        clip_dur = probe_duration(in_path)
    inputs = ["-i", in_path]
    chains = ["[0:a]apad[a0]"]
    mixes = ["[a0]"]
    idx = 1
    if bgm:
        vol = float(bgm.get("volume", 0.15))
        if loop:
            fin = min(0.35, clip_dur / 8)
            fout_d = min(0.35, clip_dur / 8)
        else:
            fin = min(0.8, clip_dur / 4)
            fout_d = min(1.2, clip_dur / 4)
        inputs += ["-stream_loop", "-1", "-i", str(bgm["path"])]
        chains.append(
            f"[{idx}:a]atrim=0:{clip_dur:.3f},asetpts=PTS-STARTPTS,"
            f"volume={vol:.3f},"
            f"afade=t=in:st=0:d={fin:.3f},"
            f"afade=t=out:st={max(0.0, clip_dur - fout_d):.3f}:d={fout_d:.3f}[bgm]")
        mixes.append("[bgm]")
        idx += 1
    if config.SFX:
        assets = None
        try:
            assets = _sfx.ensure()   # SFX tak boleh PERNAH mematikan render
        except Exception:
            assets = None
        if assets:
            for t in (sfx_times or []):
                if not (0 <= t < max(0.3, clip_dur - 0.2)):
                    continue
                ms = max(0, int(t * 1000))
                inputs += ["-i", str(assets["whoosh"])]
                chains.append(f"[{idx}:a]adelay={ms}:all=1,"
                              f"volume={config.SFX_VOLUME:.2f}[w{idx}]")
                mixes.append(f"[w{idx}]")
                idx += 1
            if hook_pop and clip_dur > 0.6:
                inputs += ["-i", str(assets["pop"])]
                chains.append(f"[{idx}:a]adelay=150:all=1,"
                              f"volume={max(0.2, config.SFX_VOLUME):.2f}[p{idx}]")
                mixes.append(f"[p{idx}]")
                idx += 1
    if len(mixes) < 2:
        return  # tak ada BGM/SFX yang bisa dicampur -> no-op
    aout = ("".join(mixes) +
            f"amix=inputs={len(mixes)}:duration=longest:"
            f"dropout_transition=0:normalize=0[aout]")
    tmp = str(in_path) + ".tmp.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error"] + inputs +
        ["-filter_complex", ";".join(chains + [aout]),
         "-map", "0:v", "-map", "[aout]",
         "-c:v", "copy", "-c:a", "aac", "-b:a", "128k",
         "-t", f"{clip_dur:.3f}", tmp],
        check=True, cwd=os.path.dirname(in_path) or ".")
    os.replace(tmp, in_path)


def concat_clips(paths, out_path):
    """Concat demuxer -c copy: semua sub dirender render_clip dengan parameter
    identik (codec/timebase sama) — murah, tanpa encode ulang."""
    out_path = os.path.abspath(out_path)
    lst = out_path + ".txt"
    with open(lst, "w") as fh:
        for p in paths:
            fh.write("file '" + os.path.abspath(str(p)) + "'\n")
    try:
        subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                        "-f", "concat", "-safe", "0", "-i", lst,
                        "-c", "copy", "-movflags", "+faststart", out_path],
                       check=True)
    finally:
        try:
            os.remove(lst)
        except OSError:
            pass
