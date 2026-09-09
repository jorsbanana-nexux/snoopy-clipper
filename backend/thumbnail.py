"""
Thumbnail klip — WAJIB ada, TIDAK PERNAH gagal (hukum: selalu ada file .jpg).

Aturan desain ala thumbnail profesional (MrBeast dsb):
- wajah close-up + ekspresif (emosi > gaya) = bikin penasaran & di-klik
- kontras & warna hidup (grade ringan sama seperti klip)
- TANPA teks -> berlaku untuk SEMUA bahasa sekaligus (v2: teks via Gemini)

Rantai fallback berlapis — selalu menghasilkan file:
  1. Frame terbaik dari sumber (wajah terbesar + paling ekspresif + tajam)
  2. Frame paling tajam dari sumber (tanpa wajah) — crop tengah
  3. Frame dari klip jadi .mp4 (selalu ada)
  4. Kartu gradient sintetis (last resort — nyaris mustahil terjadi)
Semua biaya: ~6 seek + 1 resize per klip (CPU < 1-2 dtk).
"""
import logging
import math

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


def _export(img, out_path):
    import cv2
    h = img.shape[0]
    tw, th = _THUMB_W.get(1080 if h >= 1080 else 720, (1080, 1920))
    if img.shape[1] != tw or img.shape[0] != th:
        img = cv2.resize(img, (tw, th), interpolation=cv2.INTER_LANCZOS4)
    cv2.imwrite(str(out_path), img, [cv2.IMWRITE_JPEG_QUALITY, 92])


def _placeholder(out_path):
    """Last resort: kartu gradient bersih — SELALU menghasilkan file."""
    import cv2
    import numpy as np
    t = np.linspace(0, 1, 1920)[:, None]
    grad = (t * 40 + 18).repeat(1080, axis=1).astype(np.float32)
    img = np.stack([grad, grad * 0.92, grad * 0.72], axis=-1).astype(np.uint8)  # hangat
    cv2.imwrite(str(out_path), img, [cv2.IMWRITE_JPEG_QUALITY, 90])


def make_thumb(video_path, start, end, clip_mp4, out_path):
    """PINTU UTAMA — tidak pernah raise; return True kalau ada thumbnail bagus."""
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
            _export(_grade(_crop_916(fr, faces)), out_path)
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
            _export(_grade(_crop_916(frames[0], [])), out_path)
            return True
    except Exception as e:
        logger.warning("Thumbnail: klip jadi gagal (%s) -> placeholder", e)

    try:
        _placeholder(out_path)
        return False
    except Exception:
        logger.exception("Thumbnail: sesuatu yang mustahil terjadi")
        return False
