"""
Thumbnail klip — WAJIB ada, TIDAK PERNAH gagal (hukum: selalu ada file .jpg).

Aturan desain ala thumbnail profesional (MrBeast dsb):
- wajah close-up + ekspresif (emosi > gaya) = bikin penasaran & di-klik
- kontras & warna hidup (grade ringan sama seperti klip)
- TANPA teks -> berlaku untuk SEMUA bahasa sekaligus (v2: teks via Gemini)

TEKS JUDUL KHUSUS PODCAST (HANYA content_type podcast/interview — jenis
konten lain TIDAK berubah, tetap thumbnail polos seperti sebelumnya):
- judul klip dari library; putih bersih TANPA stroke/outline, hanya shadow
  hitam blur lebar yang halus menutupi area teks (3 lapis, makin luar makin
  lembut) — nyaman dilihat, teks tetap terbaca jelas
- ukuran font MENYESUAIKAN OTOMATIS ke layar (auto-fit lebar & tinggi blok)
- emoji kuning kartun tersenyum SELALU menumpang DI ATAS teks (di mana ada
  teks, di situ ada dia)
- + 1 emoji TOPIK (topic_tag dari otak Gemini: finance -> 💰, dll) di posisi
  strategis otomatis: samping teks kalau ada ruang, kalau sempit menumpang
  di ujung baris pertama — akurat no ngaco: tag tak dikenal = tanpa emoji
- font: assets/fonts/ (letakkan Liberica.ttf milikmu; pastikan lisensimu
  valid) -> fallback font sistem bold; emoji asset Microsoft Fluent 3D (MIT — bebas komersial),
  diunduh SEKALI lalu cache permanen (pola sama seperti model face & BGM)
- gagal apa pun (font/emoji/apa saja) -> thumbnail terbit TANPA teks,
  hukum utama TIDAK berubah: tidak pernah gagal menghasilkan file

Rantai fallback berlapis — selalu menghasilkan file:
  1. Frame terbaik dari sumber (wajah terbesar + paling ekspresif + tajam)
  2. Frame paling tajam dari sumber (tanpa wajah) — crop tengah
  3. Frame dari klip jadi .mp4 (selalu ada)
  4. Kartu gradient sintetis (last resort — nyaris mustahil terjadi)
Semua biaya: ~6 seek + 1 resize per klip (CPU < 1-2 dtk).
"""
import logging
import math
import re
import urllib.request
from pathlib import Path

from . import config

logger = logging.getLogger(__name__)

# posisi kandidat di dalam klip (hindari awal-awal transisi & akhiran)
_CANDIDATES = (0.18, 0.32, 0.46, 0.60, 0.75, 0.88)
_THUMB_W = {1080: (1080, 1920), 720: (720, 1280)}


def _detect_faces(frame, detector, infer_w, infer_h):
    """-> list dict (cx, cy, fw, fh, mouth, det) skala frame asli."""
    import cv2
    h, w = frame.shape[:2]
    small = cv2.resize(frame, (infer_w, infer_h))
    res = detector.detect(small)
    raw = res[1] if res is not None else None
    out = []
    if raw is not None:
        for f in raw:
            x, y, fw, fh = [float(v) for v in f[:4]]
            rm_x, rm_y, lm_x, lm_y = float(f[10]), float(f[11]), float(f[12]), float(f[13])
            mouth = math.hypot(rm_x - lm_x, rm_y - lm_y) / max(fw, 1.0)
            out.append({
                "cx": (x + fw / 2) / infer_w * w,
                "cy": (y + fh / 2) / infer_h * h,
                "fw": fw / infer_w * w, "fh": fh / infer_h * h,
                "mouth": mouth, "det": float(f[14]),
            })
    return out


def _frame_score(frame, faces):
    """Skor kelayakan: wajah besar + ekspresif + fokus tajam + exposure waras."""
    import cv2
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    sharp = cv2.Laplacian(gray, cv2.CV_64F).var()
    sharp_s = min(1.0, sharp / 300.0)
    mean = gray.mean()
    exp = 1.0 - min(abs(mean - 118) / 118.0, 1.0)  # terlalu gelap/terang = penalti
    if faces:
        best = max(faces, key=lambda f: f["fw"] * f["fh"])
        area = min(1.0, (best["fw"] * best["fh"]) / (frame.shape[0] * frame.shape[1] * 0.14))
        mouth = min(1.0, best["mouth"] / 0.32)  # mulut terbuka = ekspresi/reaksi
        return 0.45 * area + 0.20 * mouth + 0.10 * best["det"] + 0.15 * sharp_s + 0.10 * exp
    return 0.55 * sharp_s + 0.45 * exp


def _read_frames(video_path, start, end, n_positions):
    import cv2
    cap = cv2.VideoCapture(str(video_path))
    frames = []
    try:
        dur = max(0.0, end - start)
        for p in n_positions:
            cap.set(cv2.CAP_PROP_POS_MSEC, (start + dur * p) * 1000)
            ok, frame = cap.read()
            if ok and frame is not None and frame.shape[0] > 0:
                frames.append(frame)
    finally:
        cap.release()
    return frames


def _detector():
    from .facetrack import _model_path, _INFER_W, _INFER_H
    import cv2
    return cv2.FaceDetectorYN.create(
        str(_model_path()), "", (_INFER_W, _INFER_H), score_threshold=0.5)


def _pick_best(frames, detector=None):
    """Frame terbaik + wajah terbaiknya (kalau ada)."""
    best, best_score, best_faces = None, -1.0, []
    for fr in frames:
        faces = _detect_faces(fr, detector, *detector_input) if detector else []
        s = _frame_score(fr, faces)
        if s > best_score:
            best, best_score, best_faces = fr, s, faces
    return best, best_faces


detector_input = None  # diisi oleh make_thumb (infer dims)


def _crop_916(frame, faces):
    """Crop 9:16 ala thumbnail: wajah di ~40% tinggi, kepala jelas, headroom pas."""
    import cv2
    h, w = frame.shape[:2]
    if w / h >= 9 / 16:  # landscape/square -> potong kiri-kanan
        ch = h
        cw = int(h * 9 / 16)
    else:                # portrait -> potong atas-bawah
        cw = w
        ch = int(w * 16 / 9)
    if faces:
        best = max(faces, key=lambda f: f["fw"] * f["fh"])
        # wajah ideal mengisi ~30% tinggi crop -> skala crop dari ukuran wajah
        want_h = min(h, int(max(best["fh"] * 3.2, ch)))
        want_w = int(want_h * 9 / 16)
        want_w = min(want_w, w)
        cx = int(max(want_w / 2, min(best["cx"], w - want_w / 2)))
        # posisi wajah di ~40% dari atas crop
        cy = int(max(want_h * 0.40, best["cy"]))
        cy = int(min(cy, h - want_h + want_h * 0.40)) if want_h < h else h // 2
        x0 = int(max(0, min(cx - want_w // 2, w - want_w)))
        y0 = int(max(0, min(cy - int(want_h * 0.40), h - want_h)))
        return frame[y0:y0 + want_h, x0:x0 + want_w]
    x0 = max(0, (w - cw) // 2)
    y0 = max(0, (h - ch) // 2)
    return frame[y0:y0 + ch, x0:x0 + cw]


def _grade(img):
    """Kontras & warna hidup ala thumbnail (murah, CPU): eq + saturasi + unsharp."""
    import cv2
    import numpy as np
    # kontras lembut + saturasi naik ~18%
    out = cv2.convertScaleAbs(img, alpha=1.10, beta=4)
    hsv = cv2.cvtColor(out, cv2.COLOR_BGR2HSV).astype(np.float32)
    hsv[..., 1] = np.clip(hsv[..., 1] * 1.18, 0, 255)
    out = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)
    # unsharp ringan
    blur = cv2.GaussianBlur(out, (3, 3), 0)
    return cv2.addWeighted(out, 1.55, blur, -0.55, 0)


# ---------------- teks judul khusus podcast ----------------

# topic_tag dari OTAK (Gemini) -> Microsoft Fluent 3D Emoji (MIT — bebas
# komersial, lebih longgar dari font/asset lain di project ini).
# Nilai = path asset di repo fluentui-emoji (tanpa ekstensi .png).
# Tag tak dikenal / gagal unduh -> TIDAK ada emoji (tidak pernah ngaco).
_TOPIC_EMOJI = {
    "finance": "Money bag/3D/money_bag_3d",
    "ekonomi": "Money bag/3D/money_bag_3d",
    "crypto": "Gem stone/3D/gem_stone_3d",
    "investasi": "Chart increasing/3D/chart_increasing_3d",
    "love": "Two hearts/3D/two_hearts_3d",
    "fitness": "Flexed biceps/Default/3D/flexed_biceps_3d_default",
    "food": "Hamburger/3D/hamburger_3d",
    "tech": "Laptop/3D/laptop_3d",
    "gaming": "Video game/3D/video_game_3d",
    "music": "Musical note/3D/musical_note_3d",
    "travel": "Airplane departure/3D/airplane_departure_3d",
    "edukasi": "Graduation cap/3D/graduation_cap_3d",
    "science": "Microscope/3D/microscope_3d",
    "health": "Pill/3D/pill_3d",
    "sports": "Soccer ball/3D/soccer_ball_3d",
    "drama": "Fire/3D/fire_3d",
    "motivation": "Rocket/3D/rocket_3d",
    "crime": "Magnifying glass tilted right/3D/magnifying_glass_tilted_right_3d",
    "family": "House/3D/house_3d",
    "cars": "Automobile/3D/automobile_3d",
    "nature": "Herb/3D/herb_3d",
    "business": "Briefcase/3D/briefcase_3d",
    "career": "Briefcase/3D/briefcase_3d",
    "history": "Scroll/3D/scroll_3d",
    "berita": "Newspaper/3D/newspaper_3d",
    "politik": "Newspaper/3D/newspaper_3d",
    "spiritual": "Folded hands/Default/3D/folded_hands_3d_default",
    "comedy": "Face with tears of joy/3D/face_with_tears_of_joy_3d",
    "psychology": "Brain/3D/brain_3d",
    "movie": "Clapper board/3D/clapper_board_3d",
    "book": "Open book/3D/open_book_3d",
    "ai": "Robot/3D/robot_3d",
    "law": "Balance scale/3D/balance_scale_3d",
    "warning": "Police car light/3D/police_car_light_3d",
    "celebrity": "Star/3D/star_3d",
}
_SMILEY = "Beaming face with smiling eyes/3D/beaming_face_with_smiling_eyes_3d"  # selalu di atas teks, tengah presis
_EMOJI_URL = ("https://raw.githubusercontent.com/microsoft/fluentui-emoji/main/assets/"
              "{}.png")

# shadow hitam: (radius sbg fraksi lebar, alpha) — dari lapis terluar paling
# lembut ke terdalam: 4 lapis = "radius jauh, halus menutupi layar" tapi
# TIDAK terlalu pekat (alpha maksimal 160 — tetap enak dilihat).
_SHADOW = ((0.045, 45), (0.028, 65), (0.014, 110), (0.005, 160))
_TEXT_W_FRAC = 0.90        # lebar maksimum blok teks (diperlebar: teks lebih besar)
_TEXT_BOTTOM_FRAC = 0.885   # dasar blok teks dari atas layar
_TEXT_MAX_LINES = 3
_TEXT_SIZE_FRAC = 0.075     # titik awal ukuran font (fraksi tinggi) — auto-fit turun
_TEXT_MAX_BLOCK_FRAC = 0.40
_LINE_SPACING = 1.08   # rapat-padat: baris berhimpit rapi, shadow tetap bernafas


def _font_candidates():
    """Urutan font teks podcast — yang pertama ADA yang dipakai.
    1) THUMB_FONT_FILE (config) 2) assets/fonts/ (mis. Liberica milikmu)
    3) font sistem bold (Liberation di Docker, DejaVu di Linux umum)."""
    cands = []
    if config.THUMB_FONT_FILE:
        cands.append(Path(config.THUMB_FONT_FILE))
    try:                                    # Milky Moringa (owner 2026-09-12)
        from . import fontdisplay
        mf = fontdisplay.ensure()
        if mf:
            cands.append(mf)
    except Exception:
        pass
    fdir = config.BASE_DIR / "assets" / "fonts"
    if fdir.is_dir():
        cands += sorted(p for p in fdir.iterdir()
                        if p.suffix.lower() in (".ttf", ".otf"))
    cands += [
        Path("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        Path("/usr/share/fonts/TTF/DejaVuSans-Bold.ttf"),
        Path("C:/Windows/Fonts/arialbd.ttf"),
        Path("C:/Windows/Fonts/impact.ttf"),
    ]
    return cands


def _emoji_img(path, size):
    """PNG Fluent 3D (MIT) — diunduh SEKALI lalu cache permanen di models/emoji/.
    Gagal unduh -> None (thumbnail tetap terbit, hanya tanpa emoji)."""
    import urllib.parse
    from PIL import Image
    p = config.MODELS_DIR / "emoji" / (path.replace("/", "__") + ".png")
    try:
        if not p.exists():
            p.parent.mkdir(parents=True, exist_ok=True)
            urllib.request.urlretrieve(_EMOJI_URL.format(urllib.parse.quote(path)), p)
    except Exception as e:
        logger.warning("Thumbnail: emoji %s tak terunduh (%s) -> tanpa emoji", code, e)
        return None
    try:
        img = Image.open(p)
        img.load()
        return img.convert("RGBA").resize((size, size), Image.LANCZOS)
    except Exception as e:
        logger.warning("Thumbnail: emoji %s tak terbaca (%s)", code, e)
        return None


def _wrap_lines(draw, text, font, max_w, max_lines):
    """Pecah teks jadi baris yang muat max_w — diukur nyata, bukan tebakan huruf.
    Kata superpanjang dipaksa potong per karakter — tidak pernah meluber."""
    words = text.split()
    if not words:
        return []
    lines, cur = [], ""
    for wd in words:
        t = wd if not cur else cur + " " + wd
        if draw.textlength(t, font=font) <= max_w or not cur:
            if not cur and draw.textlength(wd, font=font) > max_w:
                for ch in wd:  # kata tunggal melampaui lebar -> potong paksa
                    if cur and draw.textlength(cur + ch, font=font) > max_w:
                        lines.append(cur)
                        cur = ch
                    else:
                        cur += ch
                continue
            cur = t
        else:
            lines.append(cur)
            cur = wd
    if cur:
        lines.append(cur)
    return lines[:max_lines]


def _podcast_text(img, title, content_type, topic_tag):
    """Overlay teks judul HANYA utk podcast/interview — TIDAK PERNAH raise.
    Gagal apa pun -> img dikembalikan apa adanya (thumbnail tetap terbit)."""
    if (not config.THUMB_TEXT or not title
            or content_type not in ("podcast", "interview")):
        return img
    try:
        import cv2
        import numpy as np
        from PIL import Image, ImageDraw, ImageFilter, ImageFont

        h, w = img.shape[:2]
        fp = next((c for c in _font_candidates() if c.is_file()), None)
        if fp is None:
            logger.warning("Thumbnail: tak ada font ttf -> teks podcast dilewati")
            return img

        # judul bersih: buang karakter emoji (mungkin jadi kotak tofu di font teks)
        text = re.sub(r"[\U0001F000-\U0001FAFF\u2600-\u27BF\uFE0F\u200D"
                      r"\u2B00-\u2BFF\u2190-\u21FF]", "", str(title))
        text = " ".join(text.split()).upper()
        if not text:
            return img

        # UKURAN OTOMATIS: mulai besar lalu mengecil sampai blok muat layar
        max_w = int(w * _TEXT_W_FRAC)
        size = int(h * _TEXT_SIZE_FRAC)
        font = ImageFont.truetype(str(fp), size)
        probe = ImageDraw.Draw(Image.new("L", (4, 4)))
        lines = _wrap_lines(probe, text, font, max_w, _TEXT_MAX_LINES)
        line_h = int(size * _LINE_SPACING)
        while size > 24 and (
                not lines
                or any(probe.textlength(l, font=font) > max_w for l in lines)
                or line_h * len(lines) > int(h * _TEXT_MAX_BLOCK_FRAC)):
            size = int(size * 0.92)
            font = ImageFont.truetype(str(fp), size)
            lines = _wrap_lines(probe, text, font, max_w, _TEXT_MAX_LINES)
            line_h = int(size * _LINE_SPACING)
        if not lines:
            return img

        # posisi per baris: blok duduk di bawah layar, tiap baris tengah horizontal
        block_h = line_h * len(lines)
        block_top = int(h * _TEXT_BOTTOM_FRAC) - block_h
        pos = []
        for i, line in enumerate(lines):
            lw = int(probe.textlength(line, font=font))
            pos.append((int((w - lw) / 2), block_top + i * line_h, line, lw))

        base = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB)).convert("RGBA")

        # SHADOW hitam halus (tanpa outline sama sekali) — 3 lapis bertumpuk:
        # makin ke luar makin lebar & transparan = glow hitam lembut menyatu
        for frac, alpha in _SHADOW:
            sh = Image.new("RGBA", base.size, (0, 0, 0, 0))
            sd = ImageDraw.Draw(sh)
            for x, y, line, _ in pos:
                sd.text((x, y), line, font=font, fill=(0, 0, 0, alpha))
            sh = sh.filter(ImageFilter.GaussianBlur(max(2, int(w * frac))))
            base.alpha_composite(sh)

        # TEKS putih bersih — no stroke, no outline, hanya shadow di belakang
        d = ImageDraw.Draw(base)
        for x, y, line, _ in pos:
            d.text((x, y), line, font=font, fill=(255, 255, 255, 255))

        # EMOJI KUNING TERSNYUM KARTUN — selalu menumpang DI ATAS teks
        # (posisinya persis di foto referensi: duduk di atas, menutupi sedikit)
        smiley = _emoji_img(_SMILEY, int(size * 1.5))
        if smiley is not None:
            # TENGAH PESIS horizontal layar — blok teks juga terpusat,
            # jadi smiley selalu segaris sempurna dengan blok teks
            sx = (w - smiley.width) // 2
            sy = pos[0][1] + int(size * 0.24) - smiley.height
            base.alpha_composite(smiley, (max(0, sx), max(0, sy)))

        # EMOJI TOPIK (topic_tag otak) — posisi strategis otomatis:
        # ruang samping cukup -> samping kanan blok (vertikal sejajar teks);
        # sempit -> menumpang di atas ujung kanan baris pertama (ala smiley).
        tag = str(topic_tag or "").strip().lower()
        epath = _TOPIC_EMOJI.get(tag)
        emoji = _emoji_img(epath, int(size * 1.15)) if epath else None
        if emoji is not None:
            block_right = max(x + lw for x, _, _, lw in pos)
            if block_right + int(emoji.width * 1.2) <= int(w * (1 + _TEXT_W_FRAC) / 2):
                ex = int(block_right + emoji.width * 0.35)
                ey = block_top + (block_h - emoji.height) // 2
                base.alpha_composite(emoji, (ex, max(0, ey)))
            else:
                fx, fy, _, flw = pos[0]
                ex = min(fx + flw - emoji.width, w - emoji.width - int(w * 0.04))
                ex = max(ex, int(w * 0.04))
                ey = fy + int(size * 0.20) - emoji.height
                base.alpha_composite(emoji, (ex, max(0, ey)))

        return cv2.cvtColor(np.array(base.convert("RGB")), cv2.COLOR_RGB2BGR)
    except Exception as e:
        logger.warning("Thumbnail: teks podcast dilewati (%s) — gambar asli dipakai", e)
        return img


def _export(img, out_path, title="", content_type="", topic_tag=""):
    import cv2
    h = img.shape[0]
    tw, th = _THUMB_W.get(1080 if h >= 1080 else 720, (1080, 1920))
    if img.shape[1] != tw or img.shape[0] != th:
        img = cv2.resize(img, (tw, th), interpolation=cv2.INTER_LANCZOS4)
    img = _podcast_text(img, title, content_type, topic_tag)
    cv2.imwrite(str(out_path), img, [cv2.IMWRITE_JPEG_QUALITY, 92])


def _placeholder(out_path):
    """Last resort: kartu gradient bersih — SELALU menghasilkan file."""
    import cv2
    import numpy as np
    t = np.linspace(0, 1, 1920)[:, None]
    grad = (t * 40 + 18).repeat(1080, axis=1).astype(np.float32)
    img = np.stack([grad, grad * 0.92, grad * 0.72], axis=-1).astype(np.uint8)  # hangat
    cv2.imwrite(str(out_path), img, [cv2.IMWRITE_JPEG_QUALITY, 90])


def make_thumb(video_path, start, end, clip_mp4, out_path,
               title="", content_type="", topic_tag=""):
    """PINTU UTAMA — tidak pernah raise; return True kalau ada thumbnail bagus.
    title/content_type/topic_tag hanya berperan utk overlay teks podcast —
    konten lain: perilaku PERSIS seperti sebelumnya (thumbnail polos)."""
    from pathlib import Path
    out_path = Path(out_path)
    try:
        from .facetrack import _INFER_W, _INFER_H
        global detector_input
        detector_input = (_INFER_W, _INFER_H)
        det = _detector()
    except Exception as e:
        logger.warning("Thumbnail: detector tidak siap (%s) -> jalur tanpa-wajah", e)
        det = None

    try:
        frames = _read_frames(video_path, start, end, _CANDIDATES)
        fr, faces = _pick_best(frames, det) if frames else (None, [])
        if fr is not None:
            _export(_grade(_crop_916(fr, faces)), out_path,
                    title, content_type, topic_tag)
            return True
    except Exception as e:
        logger.warning("Thumbnail: sumber gagal (%s) -> fallback klip jadi", e)

    try:
        frames = []
        for t_try in (1.0, 0.0):  # seek 1 dtk; klip pendek -> frame pertama
            frames = _read_frames(clip_mp4, t_try, t_try + 0.2, (0.5,))
            if frames:
                break
        if frames:
            _export(_grade(_crop_916(frames[0], [])), out_path,
                    title, content_type, topic_tag)
            return True
    except Exception as e:
        logger.warning("Thumbnail: klip jadi gagal (%s) -> placeholder", e)

    try:
        _placeholder(out_path)
        return False
    except Exception:
        logger.exception("Thumbnail: sesuatu yang mustahil terjadi")
        return False
