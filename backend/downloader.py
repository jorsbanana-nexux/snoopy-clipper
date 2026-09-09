"""
Unduh video dari URL platform apa pun (YouTube, TikTok, Instagram, dsb) via yt-dlp.
File cache di downloads/ — video yang sama tidak diunduh dua kali.
"""
import glob
import time
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import yt_dlp

from . import config


def _cookie_opts() -> dict:
    """Opsi cookie yt-dlp — aktif hanya kalau diaktifkan (jaga-jaga blokir YouTube)."""
    if config.COOKIES_FROM_BROWSER:
        # baca langsung dari profil browser — tanpa file apa pun
        return {"cookiesfrombrowser": (config.COOKIES_FROM_BROWSER,)}
    cf = Path(config.COOKIES_FILE or (config.BASE_DIR / "cookies.txt"))
    if cf.exists():
        return {"cookiefile": str(cf)}
    return {}


_MEDIA_EXTENSIONS = {".mp4", ".mkv", ".webm", ".mov", ".m4v", ".avi"}


def cached_media(out_base) -> Path | None:
    """Kembalikan media cache untuk ``out_base`` tanpa mengunci ke .mp4.

    ``merge_output_format`` adalah preferensi yt-dlp, bukan kontrak universal.
    Mengasumsikan .mp4 membuat jalur cache/range gagal diam-diam pada extractor
    yang hanya menyediakan WebM atau MKV.
    """
    base = Path(out_base)
    choices = [p for p in base.parent.glob(base.name + ".*")
               if p.is_file() and p.suffix.lower() in _MEDIA_EXTENSIONS
               and p.stat().st_size > 1024]
    if not choices:
        return None
    # MP4 paling kompatibel; bila tidak ada, gunakan berkas terbaru yang nyata.
    choices.sort(key=lambda p: (p.suffix.lower() != ".mp4", -p.stat().st_mtime))
    return choices[0]


def normalize_url(url: str) -> str:
    """Normalisasi URL antar-platform agar ekstraktor yt-dlp tepat.
    YouTube Kids -> YouTube biasa (video ID sama, ekstraktor utama lebih andal)."""
    import re
    m = re.match(r"^(https?://)(?:www\.|m\.)?(?:youtubekids|kids\.youtube)\.com/watch\?(.+)$",
                 (url or "").strip(), re.I)
    if m:
        vm = re.search(r"(?:^|[?&])v=([\w-]{6,})", m.group(2))
        if vm:
            return f"{m.group(1)}www.youtube.com/watch?v={vm.group(1)}"
    return url


def _youtube_profile_videos_url(url: str) -> str:
    """Arahkan homepage profil YouTube ke tab video panjang yang nyata.

    yt-dlp memperlakukan ``/@handle`` sebagai halaman tab dan mengembalikan
    playlist ``Videos``/``Shorts`` sebagai entri.  Itu bukan video yang bisa
    langsung dipilih atau diunduh.  URL ``/@handle/videos`` (begitu pula
    ``/channel/<id>/videos`` dan bentuk legacy) mengembalikan kandidat video
    sebenarnya. URL watch, shorts, dan tab yang sudah eksplisit tidak diubah.
    """
    try:
        parsed = urlsplit(url)
    except ValueError:
        return url
    host = parsed.hostname or ""
    if not (host == "youtube.com" or host.endswith(".youtube.com")):
        return url
    parts = [p for p in parsed.path.split("/") if p]
    if not parts:
        return url
    tabs = {"videos", "shorts", "streams", "playlists", "featured", "community", "about", "live"}
    if parts[-1].lower() in tabs or parts[0].lower() in {"watch", "shorts", "playlist"}:
        return url
    is_handle_home = len(parts) == 1 and parts[0].startswith("@")
    is_legacy_home = len(parts) == 2 and parts[0].lower() in {"channel", "user", "c"}
    if not (is_handle_home or is_legacy_home):
        return url
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path.rstrip("/") + "/videos",
                       parsed.query, ""))


# sinyal video anak: host kids (pasti) atau kata kunci judul/channel (petunjuk)
_KIDS_HINTS = (
    "for kids", "kids video", "kids songs", "nursery", "rhymes", "cartoon",
    "cocomelon", "lagu anak", "kartun", "anak-anak", "balita", "berhitung",
    "cerita anak", "pendidikan anak",
)


def detect_kids(url: str, title: str, uploader: str) -> bool:
    """Deteksi otomatis video anak (YouTube Kids / judul khas anak).
    Dipakai otak utk mode 'aman anak': momen lucu/edukatif, framing hangat,
    bukan klikbait dramatis. Deteksi string murni — biaya nol."""
    u = (url or "").lower()
    if "youtubekids." in u:
        return True
    hay = f"{title or ''} {uploader or ''}".lower()
    return any(h in hay for h in _KIDS_HINTS)


def get_info(url: str) -> dict:
    """Ambil metadata video (id, judul, durasi) tanpa download. Cepat."""
    url = normalize_url(url)
    opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": True,
        **_cookie_opts(),
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    return {
        "id": info.get("id") or info.get("webpage_url", "video"),
        "title": info.get("title") or "Untitled",
        "duration": float(info.get("duration") or 0),
        "uploader": info.get("uploader") or "",
    }


def resolve_url(url: str, max_entries=None):
    """Deteksi jenis URL: video tunggal atau CHANNEL/PROFILE/PLAYLIST.
    Platform-agnostik (semua yang didukung yt-dlp). Channel/profile dibaca
    FLAT (entri ringan — cepat, tanpa ekstraksi per video).
    Return ("video", info, None) atau ("channel", {"title","uploader"}, entries)."""
    url = _youtube_profile_videos_url(normalize_url(url))
    opts = {
        "quiet": True, "no_warnings": True, "skip_download": True,
        "noplaylist": True,             # watch?v=..&list=.. tetap dianggap video tunggal
        "extract_flat": "in_playlist",  # channel/profile -> daftar entri ringan
        "playlistend": int(max_entries or config.CHANNEL_MAX_CANDIDATES),
        **_cookie_opts(),
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    if info.get("_type") in ("playlist", "multi_video") and info.get("entries"):
        return "channel", {
            "title": info.get("title") or info.get("uploader")
                      or info.get("channel") or "Channel",
            "uploader": info.get("uploader") or info.get("channel") or "",
        }, list(info["entries"])
    return "video", info, None


def pick_channel_best(entries):
    """Pilih video TERBAIK dari channel — DIPERHITUNGKAN, bukan random:
    skor = popularitas (views) x faktor durasi-wajar-untuk-klip x bonus
    posisi terbaru. Live/upcoming & shorts kurang layak disaring.
    Return (url, judul, alasan) atau (None, "", alasan)."""
    cands = []
    n = len(entries)
    for pos, e in enumerate(entries):
        if not e:
            continue
        if (e.get("live_status") or "") in ("is_live", "post_live", "is_upcoming"):
            continue  # live/upcoming tak bisa dipotong jadi klip
        url = e.get("url") or e.get("webpage_url")
        if not url:
            continue
        views = float(e.get("view_count") or 0)
        dur = float(e.get("duration") or 0)
        dur_f = 1.0
        if dur and dur < 90:
            dur_f = max(0.35, dur / 90.0)      # terlalu pendek: bahan klip tipis
        elif dur > 3 * 3600:
            dur_f = 0.7                        # sangat panjang: unduhan berat
        recent_f = 1.0 + 0.5 * (n - pos) / max(1, n)  # terbaru sedikit diunggulkan
        cands.append((views * dur_f * recent_f, url,
                      e.get("title") or "Video", views, dur))
    if not cands:
        return None, "", "channel tidak punya video yang bisa diproses"
    cands.sort(key=lambda c: c[0], reverse=True)
    best = cands[0]
    views = best[3]
    if views >= 1_000_000:
        vtxt = f"{views / 1_000_000:.1f} juta views"
    elif views > 0:
        vtxt = f"{int(views):,} views".replace(",", ".")
    else:
        vtxt = "video terbaru (views tak tersedia)"
    why = vtxt
    if best[4]:
        why += f" • durasi {int(best[4] // 60)}m — pas untuk dijadikan klip"
    return best[1], best[2], why


def download(url: str, out_base, time_range=None, on_progress=None) -> str:
    """Unduh video (maks config.MAX_SOURCE_HEIGHT) -> path file mp4 hasil merge.
    time_range=(start, end) detik: unduh HANYA rentang itu (download_ranges)
    — platform tanpa dukungan rentang otomatis fallback unduh penuh lalu memotong.
    on_progress(fraksi 0..1): callback live utk indikator unduh (throttle 2 dtk,
    aman: error di hook tidak pernah menggagalkan unduhan)."""
    url = normalize_url(url)
    h = config.MAX_SOURCE_HEIGHT
    if time_range:
        # unduhan rentang: WAJIB rantai tanpa filter ext (filter [ext=mp4] +
        # force_keyframes membuat stream video hilang diam-diam di beberapa video)
        fmt = (
            f"bestvideo[height<={h}]+bestaudio/"
            f"best[height<={h}]/best"
        )
    else:
        fmt = (
            f"bestvideo[height<={h}][ext=mp4]+bestaudio[ext=m4a]/"
            f"bestvideo[height<={h}]+bestaudio/"
            f"best[height<={h}]/best"
        )
    opts = {
        "format": fmt,
        "outtmpl": str(out_base) + ".%(ext)s",
        "merge_output_format": "mp4",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "concurrent_fragment_downloads": 4,
        **_cookie_opts(),
    }
    if time_range:
        from yt_dlp.utils import download_range_func
        opts["download_ranges"] = download_range_func(None, [(time_range[0], time_range[1])])
        opts["force_keyframes_at_cuts"] = True  # potongan akurat frame-level
    if on_progress:
        _last = [0.0]
        def _hook(d):
            try:  # hook hanya indikator — jangan pernah gagalkan unduhan
                if d.get("status") != "downloading":
                    return
                now = time.time()
                if now - _last[0] < 2.0:  # throttle: update tiap 2 dtk saja
                    return
                _last[0] = now
                tot = d.get("total_bytes_estimate") or d.get("total_bytes") or 0
                got = d.get("downloaded_bytes") or 0
                if tot:
                    on_progress(max(0.0, min(1.0, got / tot)))
            except Exception:
                pass
        opts["progress_hooks"] = [_hook]
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        try:
            return info["requested_downloads"][0]["filepath"]
        except (KeyError, IndexError, TypeError):
            # fallback: cari file dengan prefix out_base
            for c in sorted(glob.glob(str(out_base) + ".*"), key=len):
                if c.endswith((".mp4", ".mkv", ".webm")):
                    return c
            raise RuntimeError("Download selesai tapi file video tidak ditemukan.")

def get_info_local(path) -> dict:
    """Info video dari FILE LOKAL (mode upload / file di disk) — tanpa internet."""
    import hashlib
    import subprocess
    from pathlib import Path
    path = Path(path)
    h = hashlib.md5(str(path.stat().st_size).encode() + path.stem.encode()).hexdigest()[:10]
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(path)],
        capture_output=True, text=True,
    ).stdout.strip()
    return {
        "id": f"local_{h}",
        "title": path.stem,
        "duration": float(out or 0),
        "uploader": "local",
    }


def download_audio(url: str, out_base) -> str:
    """Unduh HANYA audio (m4a/opus) — jalur fallback hemat untuk whisper full."""
    url = normalize_url(url)
    opts = {
        "format": "bestaudio[ext=m4a]/bestaudio/best",
        "outtmpl": str(out_base) + ".%(ext)s",
        "noplaylist": True,
        "quiet": True, "no_warnings": True, "noprogress": True,
        **_cookie_opts(),
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        try:
            return info["requested_downloads"][0]["filepath"]
        except (KeyError, IndexError, TypeError):
            for c in sorted(glob.glob(str(out_base) + ".*"), key=len):
                if c.split(".")[-1] in ("m4a", "opus", "webm", "mp3", "ogg", "mp4"):
                    return c
            raise RuntimeError("Download audio selesai tapi file tidak ditemukan.")
