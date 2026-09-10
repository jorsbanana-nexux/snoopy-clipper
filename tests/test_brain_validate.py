"""Kontrak otak v7: verifikasi silang — sentakan timestamp ke batas kalimat.

Jalur caption tidak punya word-timestamp (words=[]): sebelumnya timestamp klip
mentah-mentah dari LLM. Sekarang start/end disentak ke batas BARIS terdekat —
potongan tidak boleh nyangkal di tengah kalimat atau memotong pay-off.
"""
from backend import brain


def test_validate_snaps_to_line_boundaries_when_no_words():
    """Jalur caption: start/end bergeser ke awal/akhir baris terdekat."""
    lines = [
        {"start": 10.0, "end": 14.0, "text": "kalimat a"},
        {"start": 15.2, "end": 19.0, "text": "kalimat b"},
    ]
    out = brain._validate(
        [{"start": 11.9, "end": 18.6, "title": "x", "score": 8}],
        [], 100.0, lines=lines,
    )
    assert out[0]["start"] == 10.0   # awal baris terdekat, bukan tengah kalimat
    assert out[0]["end"] == 19.0     # akhir baris terdekat, pay-off tidak terpotong


def test_validate_words_beat_lines_when_both_exist():
    """Word-timestamp (whisper) lebih presisi — selalu diutamakan."""
    words = [{"start": 11.0, "end": 11.4, "text": "w"},
             {"start": 29.0, "end": 29.5, "text": "w2"}]
    lines = [{"start": 10.0, "end": 30.0, "text": "a"}]
    out = brain._validate(
        [{"start": 11.2, "end": 29.4, "title": "x", "score": 8}],
        words, 100.0, lines=lines,
    )
    assert out[0]["start"] == 11.0 and out[0]["end"] == 29.5


def test_validate_far_timestamp_left_untouched():
    """Timestamp jauh dari semua batas (>2 dtk) tidak dipaksa geser."""
    lines = [{"start": 10.0, "end": 14.0, "text": "a"}]
    out = brain._validate(
        [{"start": 30.0, "end": 50.0, "title": "x", "score": 8}],
        [], 100.0, lines=lines,
    )
    assert out[0]["start"] == 30.0 and out[0]["end"] == 50.0


def test_validate_drops_overlap_and_too_short():
    lines = [{"start": float(i), "end": float(i) + 0.9, "text": "l"} for i in range(100)]
    m1 = {"start": 10.0, "end": 40.0, "title": "a", "score": 9}
    m2 = {"start": 12.0, "end": 45.0, "title": "b", "score": 8}  # tumpang tindih
    m3 = {"start": 60.0, "end": 61.0, "title": "c", "score": 7}  # terlalu pendek
    out = brain._validate([m1, m2, m3], [], 100.0, lines=lines)
    assert len(out) == 1 and out[0]["title"] == "a"


def test_prompt_v7_has_cross_verification_step():
    """LANGKAH 4 verifikasi silang wajib ada di prompt final."""
    tr = {"language": "id", "words": [], "lines": [{"start": 0.0, "end": 2.0, "text": "tes"}]}
    prompt = brain._build_prompt(tr, 60.0, None, 0)
    assert "LANGKAH 4" in prompt and "VERIFIKASI SILANG" in prompt
    assert "TIGA DETIK PERTAMA" in prompt
