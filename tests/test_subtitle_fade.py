"""Kontrak: frasa subtitle menutup dengan fade-out + blur halus (bukan potong keras)."""
from backend import subtitles


def _words():
    return [
        {"start": 0.0, "end": 0.4, "text": "ini"},
        {"start": 0.4, "end": 0.9, "text": "tes"},
    ]


def test_fade_out_blur_present():
    ass = subtitles.build_ass(_words(), None, None, 1080, 1920, 0.0, 3.0)
    assert "\\fad(0,220)" in ass          # fade-out alpha halus di akhir frasa
    assert "\\blur2.6" in ass             # blur mini membesar saat memudar


def test_fade_out_clamped_for_short_phrase():
    ass = subtitles.build_ass(_words(), None, None, 1080, 1920, 0.0, 0.3)  # frasa 300ms
    # fade tidak boleh lebih panjang dari frasanya sendiri
    assert "\\fad(0,300)" in ass
