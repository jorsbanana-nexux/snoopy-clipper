"""Uji thumbnail: rantai fallback berlapis — TIDAK PERNAH gagal menghasilkan file."""
import os, subprocess, sys, types
from pathlib import Path

os.environ.setdefault("THUMBNAIL", "1")
sys.path.insert(0, ".")

import cv2
import numpy as np

from backend import config, thumbnail

TMP = Path("tests/_thumb_tmp")
TMP.mkdir(exist_ok=True)


def _src_video(name="src.mp4", w=640, h=360, sec=3):
    """Video sintetis bergerak (tanpa wajah) — cukup untuk jalur non-wajah."""
    p = TMP / name
    subprocess.run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", f"testsrc2=size={w}x{h}:rate=15:duration={sec}",
        "-pix_fmt", "yuv420p", str(p),
    ], check=True)
    return p


def test_dari_sumber():
    src = _src_video()
    clip = TMP / "clip.mp4"
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                    "-i", str(src), "-t", "2", str(clip)], check=True)
    out = TMP / "clip_01.jpg"
    ok = thumbnail.make_thumb(src, 0.0, 2.0, clip, out)
    img = cv2.imread(str(out))
    assert img is not None, "jpg harus selalu terbentuk"
    assert out.stat().st_size > 5000, "jpg tidak boleh nyaris kosong"
    assert img.shape == (1280, 720, 3), img.shape  # sumber 360p -> 720x1280
    assert ok is True


def test_fallback_ke_klip_jadi():
    clip = TMP / "clip.mp4"
    if not clip.exists():
        _src_video("clip.mp4")
    out = TMP / "fb_clip.jpg"
    ok = thumbnail.make_thumb(TMP / "tidak_ada.mp4", 0.0, 2.0, clip, out)
    assert out.exists() and out.stat().st_size > 3000
    assert ok is True  # dari klip jadi tetap dianggap sukses


def test_fallback_placeholder():
    out = TMP / "last.jpg"
    ok = thumbnail.make_thumb(TMP / "tidak_ada.mp4", 0.0, 2.0, TMP / "juga_tidak.mp4", out)
    img = cv2.imread(str(out))
    assert img is not None and img.shape == (1920, 1080, 3), "placeholder 1080x1920"
    assert ok is False  # tandai bukan sumber bagus, tapi file ADA


def test_crop_916_pusat_landscape():
    frame = np.zeros((720, 1280, 3), np.uint8)
    frame[:, :, 2] = 200
    c = thumbnail._crop_916(frame, [])
    assert abs(c.shape[1] / c.shape[0] - 9 / 16) < 0.01, c.shape


def test_crop_916_dengan_wajah():
    frame = np.zeros((720, 1280, 3), np.uint8)
    faces = [{"cx": 1000.0, "cy": 400.0, "fw": 180.0, "fh": 240.0}]
    c = thumbnail._crop_916(frame, faces)
    assert c.shape[1] / c.shape[0] <= 9 / 16 + 0.01
    assert c.shape[1] <= 1280 and c.shape[0] <= 720


def test_grade_dan_export():
    frame = np.full((400, 400, 3), 90, np.uint8)
    g = thumbnail._grade(frame)
    assert g.shape == frame.shape and g.dtype == np.uint8
    out = TMP / "grade.jpg"
    thumbnail._export(g, out)
    assert cv2.imread(str(out)) is not None


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except Exception as e:
                fails += 1
                print(f"FAIL {name}: {e!r}")
    sys.exit(1 if fails else 0)
