"""
Subtitle v3.1 — hasil BEDAH FRAME video tutorial MrBeast (pf9vd2sny0M):
- Huruf Besar Di Awal, ukuran WAJAR (±4.94% tinggi frame — +3% utk keterbacaan HP).
- PROGRESSIVE REVEAL: kata muncul satu-satu saat diucapkan (alpha pop-in).
- PRESISI KATA: timing pop & karaoke dihitung presisi per-ms (TANPA pembulatan
  kasar 10ms), MICRO-LEAD 25ms (mata melihat sesaat sebelum telinga mendengar
  -> terasa nyambung pas), dan bounce selalu TUNTAS sebelum kata berikutnya.
- SPLIT LAYER (duo): bila otak mendeteksi frame terbelah ATAS-BAWAH (podcast
  di atas + gameplay/demo di bawah, pembicara nunjukin sesuatu, dll),
  subtitle dirender DUA KALI — tengah belahan atas & tengah belahan bawah
  (penonton dua-duanya tetap kebaca). Perpindahan single<->duo di tengah
  klip memakai crossfade pendek (mulus, tanpa loncat). Frame NORMAL:
  TIDAK tersentuh sama sekali — posisi & perilaku identik v3.
- TEKS BERSIH: tanpa titik/koma, spasi rapi (tanda seru/tanya dipertahankan).
- BOUNCE: tiap kata pop dengan overshoot scale lalu settle.
- KARAOKE STABILO: kata AKTIF biru stabilo saat diucapkan -> putih begitu selesai.
- SMART location: hindari wajah pembicara (mode single; mode duo otomatis
  ke tengah tiap belahan, aman dari kedua zona).
- SMART size: font adaptif memastikan muat lebar frame.
Implementasi ASS murni: 1 event per frasa per posisi, per-kata override block
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

_MICRO_LEAD_MS = 25      # mata melihat teks sesaat SEBELUM kata terdengar
_TRANS_MS = 120          # crossfade perpindahan single<->duo
_MIN_SEG_SEC = 0.4       # anti-flicker: layout tak gonta-ganti lebih rapat dari ini
_DUO_Y_TOP = 0.25        # tengah belahan atas
_DUO_Y_BOT = 0.75        # tengah belahan bawah


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


def _font_size(n_chars: int, width: int, height: int) -> int:
    """Ukuran font adaptif: baseline wajar (±4.94% tinggi frame, +3% utk HP),
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


def _layout_segments(clip_dur: float, layout, layout_events):
    """Segmen layout sepanjang klip: [(t_mulai, t_akhir, 'single'|'duo')].
    Default single. 'duo' + perubahan tengah-klip hanya aktif kalau
    config.SUBTITLE_SPLIT_LAYER — semua input otak divalidasi keras
    (t di luar klip dibuang, gonta-ganti < _MIN_SEG_SEC diabaikan)."""
    if not config.SUBTITLE_SPLIT_LAYER:
        return [(0.0, clip_dur, "single")]
    lay = "duo" if str(layout or "").lower() == "duo" else "single"
    pts = [(0.0, lay)]
    for ev in (layout_events or []):
        if not isinstance(ev, dict):
            continue
        try:
            t = float(ev.get("t", ev.get("time")))
        except (TypeError, ValueError):
            continue
        l = "duo" if str(ev.get("layout", "")).lower() == "duo" else "single"
        if (0.05 < t < clip_dur - 0.05 and l != pts[-1][1]
                and t - pts[-1][0] >= _MIN_SEG_SEC):
            pts.append((t, l))
    return [(pts[i][0], pts[i + 1][0] if i + 1 < len(pts) else clip_dur, pts[i][1])
            for i in range(len(pts))]


def _parts(chunk: list, clip_start: float, ev_start: float) -> str:
    """Override block per kata (karaoke + pop) — waktu relatif EVENT (syarat \\t).
    PRESISI: ms penuh tanpa pembulatan; micro-lead 25ms; bounce tuntas
    sebelum kata berikutnya mulai."""
    hl_ms = max(10, config.KARAOKE_FADE_MS)
    pop = config.SUBTITLE_POP * 100
    ms = config.SUBTITLE_POP_MS
    parts = []
    for i, w in enumerate(chunk):
        wr = max(0.0, w["start"] - clip_start - ev_start)
        we = max(wr, w["end"] - clip_start - ev_start)
        text = _apply_case(_safe(_clean(w["text"])))
        fade = max(0, int(wr * 1000) - _MICRO_LEAD_MS)   # ms presisi + micro-lead
        fede = max(fade, int(we * 1000))                  # akhir kata (ms presisi)
        settle_end = fade + ms * 2 + 40                   # bounce harus tuntas
        if i + 1 < len(chunk):
            nxt = max(0, int(max(0.0, chunk[i + 1]["start"]
                                        - clip_start - ev_start) * 1000) - _MICRO_LEAD_MS)
            if nxt > fade + ms:
                settle_end = min(settle_end, nxt)
        parts.append(
            "{\\alpha&HFF&"
            f"\\t({fade},{fade + 45},\\alpha&H00&)"      # pop-in lebih halus (45ms)
            f"\\fscx100\\fscy100\\c&HFFFFFF&"
            f"\\t({fade},{fade + ms},\\fscx{pop:.0f}\\fscy{pop:.0f})"
            f"\\t({fade + ms},{settle_end},\\fscx100\\fscy100)"
            # karaoke: biru stabilo HANYA selama kata ini diucapkan,
            # lalu kembali putih — biru berjalan mengikuti ucapan.
            f"\\t({fade},{min(fade + hl_ms, fede)},\\c&H{config.HIGHLIGHT_COLOR}&)"
            f"\\t({fede},{fede + hl_ms},\\c&HFFFFFF&)"
            f"}}{text} "
        )
    return "".join(parts).strip()


def build_ass(words: list, focus_y: list, vision: dict, width: int, height: int,
              clip_start: float, clip_end: float,
              layout=None, layout_events=None) -> str:
    """Bangun file ASS lengkap untuk satu klip (waktu relatif terhadap klip).
    vision = data dari facetrack.track() untuk smart placement (boleh None).
    layout/layout_events = deteksi SPLIT LAYER dari otak (boleh kosong/None
    -> perilaku identik v3, frame normal tak tersentuh)."""
    fs_base = int(height * config.SUBTITLE_SIZE_FRAC)
    ol = max(4, int(fs_base * 0.045))
    events = []
    clip_dur = clip_end - clip_start
    chunks = _chunks(words)
    segs = _layout_segments(clip_dur, layout, layout_events)
    for ci, chunk in enumerate(chunks):
        t0 = chunk[0]["start"] - clip_start
        t1 = chunk[-1]["end"] - clip_start + 0.12
        if t1 <= 0 or t0 >= clip_dur:
            continue
        # ---- ANTI-TUMPANG TINDIH (pembicara cepat maupun lambat) ----
        if ci + 1 < len(chunks):
            t1 = min(t1, chunks[ci + 1][0]["start"] - clip_start)
        t0 = max(0.0, t0)
        if t1 - t0 < 0.05:  # nyaris nol setelah clamp -> frasa berikut menampilkannya
            continue
        n_chars = sum(len(_clean(w["text"])) for w in chunk) + len(chunk) - 1
        fs = _font_size(n_chars, width, height)
        bord = max(4, int(fs * 0.045))
        # ---- SMART PLACEMENT (mode single): wajah + UI platform + saliency ----
        mid = (chunk[0]["start"] + chunk[-1]["end"]) / 2
        if config.PLACEMENT_SMART and vision:
            x, y_frac = placement.choose_position(
                vision, mid, n_chars, fs, width, height, config.SUBTITLE_Y_FRAC)
            y = int(height * y_frac)
        else:
            fy = _y_at(focus_y, mid)
            y = int(height * 0.38) if (fy is not None and fy > 0.55) else int(height * config.SUBTITLE_Y_FRAC)
            x = width // 2
        # ---- potong frasa per segmen layout (single <-> duo) ----
        for (s0, s1, lay) in segs:
            i0 = max(t0, s0)
            i1 = min(t1, s1)
            if i1 - i0 < 0.05:
                continue
            if lay == "duo":
                # teks SAMA persis di tengah kedua belahan (sinkron, dobel)
                positions = [(width // 2, int(height * _DUO_Y_TOP)),
                            (width // 2, int(height * _DUO_Y_BOT))]
            else:
                positions = [(x, y)]
            # transisi mulus: crossfade pendek di perbatasan single<->duo
            fin = _TRANS_MS if (s0 > 0 and i0 - s0 < 0.05) else 0
            fo = (_TRANS_MS if (s1 < clip_dur and s1 - i1 < 0.05)
                  else config.SUBTITLE_FADE_MS)
            dur_ms = int((i1 - i0) * 1000)
            fo = max(0, min(fo, dur_ms))
            fin = max(0, min(fin, dur_ms))
            # ---- FADE-OUT SATISFYING: frasa menutup memudar + blur halus ----
            blur_a, blur_b = max(0, dur_ms - fo), dur_ms
            parts = _parts(chunk, clip_start, i0)
            for (px, py) in positions:
                events.append(
                    "Dialogue: 0,%s,%s,Snoop,,0,0,0,,"
                    "{\\an5\\pos(%d,%d)\\fs%d\\bord%d\\fad(%d,%d)\\t(%d,%d,\\blur2.6)}%s"
                    % (_fmt(i0), _fmt(i1), px, py, fs, bord, fin, fo,
                       blur_a, blur_b, parts)
                )
    return _HEADER.format(w=width, h=height, font=config.SUBTITLE_FONT,
                          fs=fs_base, ol=ol) + "\n".join(events) + "\n"
