"""
Smart Placement Engine — posisi subtitle tidak pernah menutupi:
1. WAJAH & objek utama: collision bounding box -> teks digeser ke atas kepala /
   bawah dagu sampai bebas tabrakan.
2. UI SAFE ZONE platform (TikTok/Reels/Shorts): sisi kanan (like/comment/share)
   dan bawah (username/deskripsi) dijauhi; posisi ideal ~60-75% tinggi frame.
3. TEKS BAWAAN video (berita/gameplay): baris teks terdeteksi (komponen kecil
   teratur — pengganti OCR ringan) -> subtitle pindah ke area bersih.
4. SALIENCY: area yang paling menarik mata (edge density tinggi = objek utama)
   dihindari -> subtitle nangkring di area lebih tenang.

Semua deterministik & lokal (tanpa model berat — ramah PC low-spec).
Input `vision` dibangun facetrack.track() dari pass sampling yang sama
(biaya tambahan nyaris nol).
"""
from . import config

N_BANDS = 12


def _bands_of(f0: float, f1: float) -> range:
    """Index band horizontal (0=atas) yang dilalui area [f0, f1]."""
    b0 = max(0, int(f0 * N_BANDS))
    b1 = min(N_BANDS - 1, int(f1 * N_BANDS - 1e-9))
    return range(b0, b1 + 1)


def _faces_at(vision: dict, t_mid: float, window: float) -> list:
    """Semua bounding box wajah (fraksi frame) di sekitar waktu frasa."""
    boxes = []
    for t, bs in vision.get("boxes") or []:
        if abs(t - t_mid) <= window:
            boxes.extend(bs)
    return boxes


def _overlap(a, b) -> bool:
    return not (a[2] < b[0] or b[2] < a[0] or a[3] < b[1] or b[3] < a[1])


def _expand(box, k: float):
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    return (cx - w * k / 2, cy - h * k / 2, cx + w * k / 2, cy + h * k / 2)


def choose_position(vision: dict, t_mid: float, n_chars: int,
                    fs: int, width: int, height: int, prefer: float):
    """
    Pilih posisi terbaik untuk SATU frasa subtitle.
    -> (x_px, y_frac). Skor = penalti collision wajah (besar)
       + teks bawaan (sedang) + saliency (kecil) + jarak dari posisi ideal.
    """
    # estimasi bounding box teks (fraksi frame) — dihitung SEBELUM render
    half_h = (fs * 1.4 / 2) / height
    half_w = min((n_chars * 0.62 * fs / 2) / width, 0.42)
    y_min = config.SUBTITLE_MIN_Y_FRAC + half_h
    y_max = 1 - config.UI_SAFE_BOTTOM - half_h - 0.01
    prefer = min(max(prefer, y_min), y_max)

    # kandidat Y: dari posisi ideal melebar ke dua arah
    cands = []
    for d in (0.0, -0.07, 0.07, -0.14, 0.14, -0.21, 0.21, -0.28, 0.28, -0.35, 0.35):
        y = prefer + d
        if y_min <= y <= y_max:
            cands.append(y)

    window = max(1.2, (vision.get("interval") or 1.0) * 1.5)
    faces = _faces_at(vision, t_mid, window)
    sal = vision.get("sal") or []
    txt = vision.get("txt") or []

    best, best_score = prefer, None
    for y in cands:
        tb = (0.5 - half_w, y - half_h, 0.5 + half_w, y + half_h)
        score = abs(y - prefer) * 4.0  # jangan jauh-jauh dari posisi ideal
        # (1) tabrakan dengan wajah -> penalti paling besar
        for fb in faces:
            if _overlap(tb, _expand(fb, 1.25)):
                score += 100
                break
        # (2) tumpang tindih teks bawaan video
        if txt:
            score += max((txt[b] for b in _bands_of(tb[1], tb[3])), default=0) * 30
        # (3) area saliency (objek utama / area ramai)
        if sal:
            score += max((sal[b] for b in _bands_of(tb[1], tb[3])), default=0) * 10
        if best_score is None or score < best_score:
            best, best_score = y, score

    # SAFE ZONE horizontal: jauhi tombol like/comment/share di kanan platform
    x = width / 2
    right_lim = width * (1 - config.UI_SAFE_RIGHT)
    if x + half_w * width > right_lim:
        x = max(half_w * width + width * 0.04, right_lim - half_w * width)
    return int(x), best
