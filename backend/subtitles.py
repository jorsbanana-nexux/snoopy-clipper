"""
Subtitle v3 — hasil BEDAH FRAME video tutorial MrBeast (pf9vd2sny0M):
- Huruf Besar Di Awal, ukuran WAJAR (±4.7% tinggi frame) ala clipper profesional, bawah layar (±80%).
- PROGRESSIVE REVEAL: kata muncul satu-satu saat diucapkan (alpha pop-in).
- TEKS BERSIH: tanpa titik/koma, spasi rapi (tanda seru/tanya dipertahankan).
- BOUNCE: tiap kata pop dengan overshoot scale lalu settle (dari analisis: 48%
  kata terlihat dalam keadaan scale-up di frame sampling).
- Warna: putih + KUNING-EMAS untuk kata penekanan (angka/kata kuat/kata terpanjang).
- SMART location: tetap hindari wajah pembicara (turun warisan v2).
- SMART size: font adaptif memastikan muat lebar frame.
Implementasi ASS murni: 1 event per frasa, per-kata override block
(alpha + \\t bounce) — ringan, tanpa efek berat.
"""
from . import config, placement

_HEADER = """[Script Info]
ScriptType: v4.00+
PlayResX: {w}
PlayResY: {h}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Snoop,{font},{fs},&H00FFFFFF,&H00FFFFFF,&H00000000,&H96000000,1,0,0,0,100,100,0,0,1,{ol},1,5,40,40,40,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

# kata penekanan ( Indonesia + Inggris) -> diberi warna emas
_EMPHASIS = {
    "gila", "banget", "wow", "keren", "paling", "besar", "hebat", "ajaib",
    "big", "huge", "crazy", "insane", "omg", "wtf", "epic", "best", "worst",
    "never", "always", "free", "million", "first", "last", "no", "yes",
}


def _fmt(t: float) -> str:
    t = max(0.0, t)
    cs = int(round(t * 100))
    h = cs // 360000
    cs %= 360000
    m = cs // 6000
    cs %= 6000
    s = cs // 100
    cs %= 100
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _safe(text: str) -> str:
    return text.replace("{", "(").replace("}", ")").replace("\n", " ")


def _clean(text: str) -> str:
    """Normalisasi tampilan: buang titik/koma/titik-dua/kutip, rapikan spasi.
    Tanda seru & tanya DIPERTAHANKAN (emosi penting di caption)."""
    import re
    text = re.sub(r"[.,;:\u2026\"'`\u201c\u201d]", "", text)
    return " ".join(text.split())


def _apply_case(text: str) -> str:
    """Huruf Besar Di Awal (title) — default; upper & normal tersedia via .env"""
    if config.SUBTITLE_CASE == "upper":
        return text.upper()
    if config.SUBTITLE_CASE == "normal":
        return text
    return " ".join(w.capitalize() for w in text.split())


def _y_at(focus_y, t: float):
    """Posisi vertikal wajah fokus terdekat pada waktu t (untuk penempatan pintar)."""
    if not focus_y:
        return None
    return min(focus_y, key=lambda p: abs(p[0] - t))[1]


def _chunks(words: list, max_chars=26, max_words=6) -> list:
    """Kelompokkan kata jadi frasa pendek (hasil analisis: median ±5 kata per frasa)."""
    chunks, cur = [], []
    for w in words:
        cand = cur + [w]
        text = " ".join(x["text"] for x in cand)
        too_long = cur and (
            len(text) > max_chars or len(cand) > max_words or (w["start"] - cur[-1]["end"]) > 0.8
        )
        if too_long:
            chunks.append(cur)
            cur = [w]
        else:
            cur = cand
    if cur:
        chunks.append(cur)
    return chunks


def _pick_emphasis(chunk) -> int:
    """Index kata yang di-highlight emas: kata angka/penekanan, kalau tidak ada -> terpanjang."""
    for i, w in enumerate(chunk):
        t = _clean(w["text"]).lower()
        if t in _EMPHASIS or any(c.isdigit() for c in t):
            return i
    return max(range(len(chunk)), key=lambda i: len(chunk[i]["text"]))


def _font_size(n_chars: int, width: int, height: int) -> int:
    """Ukuran font adaptif: baseline wajar (±4.7% tinggi frame),
    mengecil bertingkat kalau frasa panjang, dan dijamin muat lebar frame."""
    fs = int(height * config.SUBTITLE_SIZE_FRAC)
    if n_chars > 8:
        fs = int(fs * 0.80)
    if n_chars > 13:
        fs = int(fs * 0.80)
    if n_chars > 18:
        fs = int(fs * 0.85)
    # frasa panjang dibungkus jadi 2 baris (WrapStyle 0) -> batas lebar 2 baris
    fit = int(2 * width * 0.92 / (n_chars * 0.62))  # lebar rata-rata huruf ±0.62x fs
    return max(30, min(fs, fit))


def build_ass(words: list, focus_y: list, vision: dict, width: int, height: int,
              clip_start: float, clip_end: float) -> str:
    """Bangun file ASS lengkap untuk satu klip (waktu relatif terhadap klip).
    vision = data dari facetrack.track() untuk smart placement (boleh None)."""
    fs_base = int(height * config.SUBTITLE_SIZE_FRAC)
    ol = max(4, int(fs_base * 0.045))
    events = []
    clip_dur = clip_end - clip_start
    chunks = _chunks(words)
    for ci, chunk in enumerate(chunks):
        t0 = chunk[0]["start"] - clip_start
        t1 = chunk[-1]["end"] - clip_start + 0.12
        if t1 <= 0 or t0 >= clip_dur:
            continue
        # ---- ANTI-TUMPANG TINDIH (pembicara cepat maupun lambat) ----
        # Ekor +0.12 dtk jangan pernah melewati awal frasa berikutnya;
        # timestamp whisper yang saling sedikit overlap pun ikut di-clamp.
        if ci + 1 < len(chunks):
            t1 = min(t1, chunks[ci + 1][0]["start"] - clip_start)
        t0 = max(0.0, t0)
        if t1 - t0 < 0.05:  # nyaris nol setelah clamp -> frasa berikut menampilkannya
            continue
        n_chars = sum(len(_clean(w["text"])) for w in chunk) + len(chunk) - 1
        fs = _font_size(n_chars, width, height)
        bord = max(4, int(fs * 0.045))
        # ---- SMART PLACEMENT: wajah + UI platform + teks bawaan + saliency ----
        mid = (chunk[0]["start"] + chunk[-1]["end"]) / 2
        if config.PLACEMENT_SMART and vision:
            x, y_frac = placement.choose_position(
                vision, mid, n_chars, fs, width, height, config.SUBTITLE_Y_FRAC)
            y = int(height * y_frac)
        else:
            fy = _y_at(focus_y, mid)
            y = int(height * 0.38) if (fy is not None and fy > 0.55) else int(height * config.SUBTITLE_Y_FRAC)
            x = width // 2
        # ---- per-kata: muncul saat diucapkan + bounce overshoot ----
        emph_i = _pick_emphasis(chunk)
        parts = []
        for i, w in enumerate(chunk):
            wr = max(0.0, w["start"] - clip_start - t0)  # relatif EVENT start (syarat \t)
            text = _apply_case(_safe(_clean(w["text"])))
            fade = max(0, int(round(wr * 100)) * 10)  # ms, dibulatkan 10ms biar rapi
            pop = config.SUBTITLE_POP * 100
            ms = config.SUBTITLE_POP_MS
            # WARN WAJIB per blok: reset ke putih, kecuali kata penekanan
            # (kalau tidak, warna emas bocor ke kata berikutnya)
            color = (f"\\c&H{config.HIGHLIGHT_COLOR}&" if i == emph_i
                     else "\\c&HFFFFFF&")
            parts.append(
                "{\\alpha&HFF&"
                f"\\t({fade},{fade + 35},\\alpha&H00&)"
                f"\\fscx100\\fscy100{color}"
                f"\\t({fade},{fade + ms},\\fscx{pop:.0f}\\fscy{pop:.0f})"
                f"\\t({fade + ms},{fade + ms * 2 + 40},\\fscx100\\fscy100)"
                f"}}{text} "
            )
        events.append(
            "Dialogue: 0,%s,%s,Snoop,,0,0,0,,"
            "{\\an5\\pos(%d,%d)\\fs%d\\bord%d}%s"
            % (_fmt(t0), _fmt(t1), x, y, fs, bord, "".join(parts).strip())
        )
    return _HEADER.format(w=width, h=height, font=config.SUBTITLE_FONT,
                          fs=fs_base, ol=ol) + "\n".join(events) + "\n"
