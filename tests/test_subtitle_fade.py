"""Kontrak: frasa subtitle menutup dengan fade-out + blur halus (bukan potong keras)."""
from backend import subtitles


def test_fade_out_blur_present():
    words = [
        {"start": 0.0, "end": 0.4, "text": "ini"},
        {"start": 0.4, "end": 0.9, "text": "tes"},
    ]
    ass = subtitles.build_ass(words, None, None, 1080, 1920, 0.0, 3.0)
    assert "\\fad(0,220)" in ass          # fade-out alpha halus di akhir frasa
    assert "\\blur2.6" in ass             # blur mini membesar saat memudar


def test_fade_out_clamped_for_short_phrase():
    # frasa satu kata ~170ms total: fade TIDAK boleh lebih panjang dari frasanya
    words = [{"start": 0.0, "end": 0.05, "text": "oke"}]
    ass = subtitles.build_ass(words, None, None, 1080, 1920, 0.0, 3.0)
    assert "\\fad(0,169)" in ass  # 0.17 dtk -> int(170)=169 (float)
