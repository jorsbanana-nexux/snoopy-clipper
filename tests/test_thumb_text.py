"""Uji teks judul thumbnail KHUSUS PODCAST — kontrak inti:
1. podcast/interview -> teks + emoji muncul, thumbnail tetap valid
2. konten lain (gaming/storytime/dst) -> byte-per-byte IDENTIK (tidak berubah)
3. input aneh (kosong, superpanjang, penuh emoji) -> TIDAK PERNAH raise
4. topic_tag tak dikenal -> tanpa emoji topik (tidak pernah emoji ngaco)
"""
import os, subprocess, sys
from pathlib import Path

os.environ.setdefault("THUMBNAIL", "1")
sys.path.insert(0, ".")

import cv2
import numpy as np

from backend import config, thumbnail

TMP = Path("tests/_thumb_tmp")
TMP.mkdir(exist_ok=True)


def _bg(h=1920, w=1080):
    """Frame sintetis ala studio (gradient hangat) — pengganti frame video."""
    t = np.linspace(60, 180, h, dtype=np.float32)[:, None]
    return np.stack([t * 0.8, t * 1.0, t * 0.7], -1).repeat(w, 1).astype(np.uint8)


def test_podcast_diberi_teks():
    """content_type=podcast -> gambar BERUBAH (teks + emoji dirender)."""
    bg = _bg()
    out = thumbnail._podcast_text(bg.copy(), "Rp100 Juta Hilang Dari Rekening!",
                                  "podcast", "finance")
    assert not np.array_equal(out, bg), "teks podcast harus mengubah gambar"
    assert out.shape == bg.shape and out.dtype == bg.dtype


def test_interview_sama_dengan_podcast():
    """Wawancara = format podcast -> juga diberi teks."""
    bg = _bg(720, 1280)
    out = thumbnail._podcast_text(bg.copy(), "Dia Akhirnya Jujur", "interview", "drama")
    assert not np.array_equal(out, bg)


def test_konten_lain_identik():
    """Jenis konten non-podcast -> byte-per-byte SAMA (tidak tersentuh)."""
    bg = _bg()
    for ct in ("gaming", "storytime", "edukasi", "vlog", "berita", "anak", "", None):
        out = thumbnail._podcast_text(bg.copy(), "Judul Apa Pun", ct, "finance")
        assert np.array_equal(out, bg), f"konten {ct!r} tidak boleh berubah"


def test_judul_aneh_tidak_pernah_raise():
    """Judul kosong/None/superpanjang/penuh emoji -> gambar tetap valid."""
    bg = _bg()
    for title in ("", None, "   ", "X" * 500, "🔥🔥 😂 judul emoji", 12345):
        out = thumbnail._podcast_text(bg.copy(), title, "podcast", "finance")
        assert out.shape == bg.shape and out.dtype == bg.dtype


def test_topic_tag_tak_dikenal_tanpa_emoji_ngaco():
    """Tag di luar _TOPIC_EMOJI -> emoji topik DILEWATI (teks tetap ada)."""
    bg = _bg()
    out = thumbnail._podcast_text(bg.copy(), "Judul Netral", "podcast", "tag-ngaco-xxx")
    assert not np.array_equal(out, bg), "teks tetap dirender walau tag tak dikenal"


def test_peta_emoji_sah():
    """Path asset Fluent 3D sahih: komponen path bersih & selalu berakhiran
    _3d(_skin) — URL raw.githubusercontent selalu terbangun benar."""
    for tag, path in {**thumbnail._TOPIC_EMOJI, "smiley": thumbnail._SMILEY}.items():
        parts = path.split("/")
        assert len(parts) >= 3, f"path emoji {tag} tak sahih: {path}"
        assert parts[-1].startswith(parts[0].replace(" ", "_").lower()), \
            f"nama file emoji {tag} tak sinkron dgn foldernya: {path}"
        assert "_3d" in parts[-1], f"bukan asset 3D: {path}"
    assert len(thumbnail._TOPIC_EMOJI) >= 30  # peta cukup luas utk topik apa pun


def test_font_candidates_tersedia():
    """Rantai font tidak kosong — minimal satu kandidat ada di lingkungan uji
    (Liberation di Docker project / DejaVu di Linux umum)."""
    cands = thumbnail._font_candidates()
    assert cands, "daftar kandidat font tidak boleh kosong"
    assert any(p.is_file() for p in cands), "minimal satu font harus ditemukan"


def test_wrap_lines_muat_dan_tak_meluber():
    """Pemenggalan baris: semua baris muat max_w; kata superpanjang dipaksa
    potong — tidak pernah ada baris yang meluber."""
    from PIL import Image, ImageDraw, ImageFont
    fp = next(p for p in thumbnail._font_candidates() if p.is_file())
    font = ImageFont.truetype(str(fp), 60)
    probe = ImageDraw.Draw(Image.new("L", (4, 4)))
    lines = thumbnail._wrap_lines(probe, "Uang Seratus Juta Rupiah", font, 300, 3)
    assert lines and all(probe.textlength(l, font=font) <= 300 for l in lines)
    lines = thumbnail._wrap_lines(probe, "SUPERPANJANG" * 20, font, 300, 3)
    assert len(lines) == 3 and all(probe.textlength(l, font=font) <= 300 for l in lines)


def test_make_thumb_end_to_end_podcast():
    """Pintu utama: thumbnail podcast + teks tetap terbit dan valid jpg."""
    clip = TMP / "pod_cast.mp4"
    if not clip.exists():
        subprocess.run([
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=15:duration=3",
            "-pix_fmt", "yuv420p", str(clip)], check=True)
    out = TMP / "pod_01.jpg"
    ok = thumbnail.make_thumb(clip, 0.0, 2.0, clip, out,
                              title="Dia Kehilangan Semuanya",
                              content_type="podcast", topic_tag="crime")
    img = cv2.imread(str(out))
    assert img is not None and out.stat().st_size > 5000
    assert ok is True


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
