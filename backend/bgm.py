"""
BGM VIRAL — Kevin MacLeod / incompetech.com (CC BY 4.0).

Pack kecil ber-mood, diunduh SEKALI per track lalu cache permanen
(mono 64 kbps ~0.5-1.5 MB per track — murah utk BGM volume rendah).
Biaya per klip: NOL unduhan, ~1 dtk mix di pass render yang sama.

Aturan pemilik: BGM WAJIB selalu ada — mood apapun dari otak selalu
diresolvenya ke track (alias + rantai fallback), tidak pernah `none`.
Kredit per track tersimpan di meta.json klip + description.txt repo.
"""
import re
import subprocess
import urllib.parse
import urllib.request
from pathlib import Path

from . import config

BASE_URL = "https://incompetech.com/music/royalty-free/mp3-royaltyfree"
CREDIT_FMT = '"{title}" — Kevin MacLeod (incompetech.com), CC BY 4.0'

# Pack inti: 8 mood x 3 track — SEMUA URL terverifikasi hidup (200 OK).
PACK = {
    "comedy": ["Monkeys Spinning Monkeys", "Fluffing a Duck", "Sneaky Snitch"],
    "upbeat": ["Carefree", "Life of Riley", "Bright Wish"],
    "chill": ["Wallpaper", "Groove Grove", "Deliberate Thought"],
    "epic": ["Heroic Age", "Achaidh Cheide", "Frozen Star"],
    "action": ["Impact Lento", "Clash Defiant", "Take the Lead"],
    "tension": ["Prelude and Action", "Hidden Agenda", "Danse Macabre"],
    "mystery": ["Sneaky Snitch", "Hidden Agenda", "Ossuary 5 - Rest"],
    "emotional": ["Heartbreaking", "Echoes of Time", "Rynos Theme"],
}
MOODS = list(PACK)

# Alias: kata lain dari otak -> mood inti (otak diminta pakai MOODS inti,
# tapi kalau dia menjawab sinonim, tetap nyambung — bukan dibuang).
ALIASES = {
    "horror": "tension", "scary": "tension", "dark": "tension",
    "dramatic": "emotional", "drama": "emotional", "sad": "emotional",
    "romantic": "emotional", "sentimental": "emotional",
    "wholesome": "upbeat", "happy": "upbeat", "funny": "comedy",
    "playful": "comedy", "quirky": "comedy",
    "corporate": "chill", "lofi": "chill", "serene": "chill",
    "documentary": "chill", "calm": "chill",
    "gaming": "action", "sports": "action", "intense": "action",
    "adventure": "epic", "motivational": "epic", "inspiring": "epic",
    "storytime": "mystery", "whodunit": "mystery", "suspense": "mystery",
}
# Mood tak dikenal -> tetap ADA bgm (urat prioritas fallback), tidak pernah kosong.
FALLBACK_CHAIN = ["upbeat", "chill", "epic", "mystery", "tension", "comedy", "action", "emotional"]


def _slug(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")


def normalize_mood(mood) -> str:
    """Mood inti dari jawaban otak apa pun — SELALU menghasilkan mood valid."""
    m = (mood or "").strip().lower()
    if m in PACK:
        return m
    m = ALIASES.get(m)
    if m:
        return m
    return FALLBACK_CHAIN[0]


def credit(title: str) -> str:
    return CREDIT_FMT.format(title=title)


def track_path(title: str) -> Path:
    return config.BGM_DIR / f"{_slug(title)}.mp3"


def pick(mood, used=()) -> str:
    """Pilih track utk mood — anti-berulang dalam job yang sama.
    Mood apapun -> SELALU ada track (fallback antar-mood, wrap-around)."""
    m = normalize_mood(mood)
    used = set(used)
    cands = [t for t in PACK[m] if t not in used]
    for m2 in FALLBACK_CHAIN:  # mood inti penuh / extra ruang -> mood serumpun
        if m2 != m:
            cands += [t for t in PACK[m2] if t not in used]
    if not cands:  # seluruh pack sudah dipakai (job raksasa) -> ulang dari awal
        cands = PACK[m][:]
    return cands[0]


def ensure_track(title: str, fetch=None, on_progress=None) -> Path:
    """Pastikan track ada di cache lokal. Unduh SEKALI + kompres mono 64k.
    Setelah itu nol unduhan selamanya (cache permanen di bgm/)."""
    cache = track_path(title)
    if cache.exists():
        return cache
    config.BGM_DIR.mkdir(parents=True, exist_ok=True)
    url = f"{BASE_URL}/{urllib.parse.quote(title)}.mp3"
    tmp = config.BGM_DIR / f"{_slug(title)}_orig.mp3"
    fetch = fetch or _fetch
    fetch(url, tmp, on_progress)
    # kompres sekali: mono 64 kbps (~0.5-1.5MB) — kualitas cukup utk bgm volume rendah
    subprocess.run(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
         "-i", str(tmp), "-ac", "1", "-b:a", "64k", str(cache)],
        check=True, capture_output=True)
    tmp.unlink(missing_ok=True)
    return cache


def _fetch(url: str, dst: Path, on_progress=None):
    """Unduh progresif (timeout 60 dtk) + hook on_progress(0..1)."""
    req = urllib.request.Request(url, headers={"User-Agent": "snoopy-clipper"})
    with urllib.request.urlopen(req, timeout=60) as r, open(dst, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        got = 0
        while True:
            chunk = r.read(65536)
            if not chunk:
                break
            f.write(chunk)
            got += len(chunk)
            if on_progress and total:
                on_progress(min(0.999, got / total))
    if not dst.exists() or dst.stat().st_size < 10000:
        raise RuntimeError(f"BGM gagal diunduh: {url}")
