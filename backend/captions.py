"""
Transkrip bawaan platform (YouTube auto-caption, dll) via yt-dlp.
Mengunduh HANYA file teks kecil (kilobytes) — selesai dalam hitungan detik.

Ini jalur tercepat untuk otak Gemini di video panjang:
menggantikan "unduh video penuh + whisper penuh" dengan "transkrip instan".
Tanpa word-timestamp (otak cukup baris; word-per-kata diambil whisper per-klip).
"""
import json
import re
import urllib.request

import yt_dlp

from .downloader import normalize_url, _cookie_opts

# urutan preferensi bahasa (id = prioritas user)
_LANG_PRIORITY = ["id", "en", "ja", "ko", "es", "pt", "zh-Hans", "zh", "ar"]


def fetch(url: str):
    """
    Ambil transkrip platform.
    -> {"language": str, "lines": [{"start","end","text"}], "words": []}
    -> None kalau platform/video tidak punya transkrip.
    """
    opts = {
        "quiet": True, "no_warnings": True, "skip_download": True,
        "noplaylist": True, **_cookie_opts(),
    }
    url = normalize_url(url)  # mis. YouTube Kids -> YouTube (transkrip tetap ketemu)
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
        manual = info.get("subtitles") or {}
        auto = info.get("automatic_captions") or {}
        lang, fmts = None, None
        for source in (manual, auto):  # subtitle manual lebih akurat dari auto
            for l in _LANG_PRIORITY + sorted(source):
                if source.get(l):
                    lang, fmts = l, source[l]
                    break
            if fmts:
                break
        if not fmts:
            return None
        by_ext = {f.get("ext"): f for f in fmts if isinstance(f, dict)}
        pick = by_ext.get("json3") or by_ext.get("vtt") or by_ext.get("srt")
        if not pick:
            return None
        if pick.get("data"):
            raw = "".join(chr(c) if isinstance(c, int) else c for c in pick["data"])
        elif pick.get("url"):
            raw = urllib.request.urlopen(pick["url"], timeout=30).read().decode("utf-8", "ignore")
        else:
            return None
        if pick.get("ext") == "json3":
            return _parse_json3(raw, lang)
        return _parse_vtt(raw, lang)


def _tokens(text: str) -> list[str]:
    """Token ringan untuk menghapus overlap auto-caption yang berjalan."""
    return re.findall(r"\S+", text or "")


def _novel_caption_text(previous: str, current: str) -> str:
    """Buang bagian awal ``current`` yang mengulang akhir cue sebelumnya.

    Auto-caption YouTube sering mengirim jendela bergulir: ``"halo apa"`` lalu
    ``"halo apa kabar"``. Mengirim keduanya mentah ke otak membuat kata dan
    momen seolah-olah berulang. Overlap suffix/prefix menjaga kalimat baru
    sambil tidak menghapus pengulangan yang bukan overlap berurutan.
    """
    prev, curr = _tokens(previous), _tokens(current)
    limit = min(len(prev), len(curr))
    for n in range(limit, 0, -1):
        if [x.casefold() for x in prev[-n:]] == [x.casefold() for x in curr[:n]]:
            return " ".join(curr[n:])
    return " ".join(curr)


def _parse_json3(raw: str, lang: str):
    """Format json3 (YouTube), dinormalisasi dari cue berjalan ke teks baru."""
    doc = json.loads(raw)
    lines, last_text, previous_window = [], "", ""
    for ev in doc.get("events", []):
        segs = [s.get("utf8", "") for s in ev.get("segs") or []]
        text = "".join(segs).replace("\n", " ").strip()
        if not text:
            continue
        if text == last_text:  # cue identik
            continue
        novel = _novel_caption_text(previous_window, text)
        previous_window = text
        if not novel:
            continue
        t = ev.get("tStartMs", 0) / 1000.0
        d = (ev.get("dDurationMs") or 2000) / 1000.0
        lines.append({"start": round(t, 2), "end": round(t + d, 2), "text": novel})
        last_text = text
    if lines:
        return {"language": lang, "lines": lines, "words": []}
    return None


_TS = re.compile(r"(?:(\d+):)?(\d+):(\d+)[.,](\d+)")

def _parse_vtt(raw: str, lang: str):
    """Parser generik VTT/SRT untuk platform non-YouTube."""
    lines, last_text = [], ""
    for block in re.split(r"\n\s*\n", raw):
        ts = _TS.findall(block)
        if len(ts) < 2:
            continue
        def sec(h, m, s, ms):
            return int(h or 0) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000.0
        start, end = sec(*ts[0]), sec(*ts[-1])
        text = " ".join(
            ln.strip() for ln in block.splitlines()
            if ln.strip() and "-->" not in ln and not _TS.search(ln)
        )
        text = re.sub(r"<[^>]+>", "", text).replace("&nbsp;", " ").replace("&amp;", "&").strip()
        if not text or text == last_text:
            continue
        lines.append({"start": round(start, 2), "end": round(end, 2), "text": text})
        last_text = text
    if lines:
        return {"language": lang, "lines": lines, "words": []}
    return None
