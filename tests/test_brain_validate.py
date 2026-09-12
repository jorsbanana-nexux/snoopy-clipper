"""Kontrak otak v7: verifikasi silang — sentakan timestamp ke batas kalimat.

Jalur caption tidak punya word-timestamp (words=[]): sebelumnya timestamp klip
mentah-mentah dari LLM. Sekarang start/end disentak ke batas BARIS terdekat —
potongan tidak boleh nyangkal di tengah kalimat atau memotong pay-off.
"""
import pytest

from backend import brain, config


@pytest.fixture(autouse=True)
def _durasi_min_lama(monkeypatch):
    """Default produksi MIN_CLIP_SEC kini 60 dtk (owner 2026-09-12). Test di
    file ini memakai klip pendek (fokus ke logika lain) -> kembalikan 15."""
    monkeypatch.setattr(config, "MIN_CLIP_SEC", 15.0)



def test_validate_snaps_to_line_boundaries_when_no_words(monkeypatch):
    """Jalur caption: start/end bergeser ke awal/akhir baris terdekat."""
    # hasil snap = klip 9.0 dtk persis -> MIN 10 (floor 0.9 = 9.0 tepat lolos)
    monkeypatch.setattr(config, "MIN_CLIP_SEC", 10.0)
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


# ---------------- v8: NATURALLY LOOPABLE CONTENT ----------------

def test_validate_loop_flag_passes_through():
    """Klip loop alami: flag + loop_note mengalir, klip normal tetap normal."""
    lines = [{"start": 5.0, "end": 45.0, "text": "isi"}]
    out = brain._validate(
        [{"start": 5.0, "end": 45.0, "title": "loop", "score": 9,
          "loop": True, "loop_note": "hook '...kenapa dia dipenjara' + bridge 'dan kamu tak akan percaya'"},
         {"start": 50.0, "end": 80.0, "title": "biasa", "score": 8}],
        [], 100.0, lines=lines + [{"start": 50.0, "end": 80.0, "text": "b"}],
    )
    loop = next(m for m in out if m["title"] == "loop")
    biasa = next(m for m in out if m["title"] == "biasa")
    assert loop["loop"] is True and "dipenjara" in loop["loop_note"]
    assert biasa["loop"] is False and biasa.get("loop_note", "") == ""


def test_loop_timestamp_is_trusted_not_dragged():
    """Klip loop: timestamp kata-presisi DIPERCAYA — snap toleransi 0.8s
    hanya merapikan noise, TIDAK menggeser ke batas yang lebih jauh.
    Klip normal (tol 2.0s) tetap disentak seperti biasa."""
    words = [{"start": 12.0, "end": 40.0, "text": "a"},
             {"start": 40.0, "end": 52.0, "text": "b"}]
    # otak loop memilih potongan kata-presisi 1.0s dari batas kata terdekat:
    # tol 0.8 -> DIPERCAYA, tidak digeser (bukan noise, memang intonasinya di situ)
    out_loop = brain._validate(
        [{"start": 13.0, "end": 51.0, "title": "loop", "score": 9, "loop": True}],
        words, 100.0,
    )
    assert out_loop[0]["start"] == 13.0 and out_loop[0]["end"] == 51.0

    # non-loop, potongan yang sama: tol 2.0 -> disentak ke batas kata
    out_biasa = brain._validate(
        [{"start": 13.0, "end": 51.0, "title": "biasa", "score": 8}],
        words, 100.0,
    )
    assert out_biasa[0]["start"] == 12.0 and out_biasa[0]["end"] == 52.0

    # noise float kecil (<0.8s) tetap dirapikan walaupun loop
    out_rapi = brain._validate(
        [{"start": 12.05, "end": 51.96, "title": "loop", "score": 9, "loop": True}],
        words, 100.0,
    )
    assert out_rapi[0]["start"] == 12.0 and out_rapi[0]["end"] == 52.0


def test_prompt_v8_has_loop_rule_and_schema():
    """Prompt wajib mengajarkan loop alami (tanpa dipaksa) + field JSON-nya."""
    tr = {"lines": [{"start": 0.0, "end": 2.0, "text": "tes"}], "language": "id"}
    p = brain._build_prompt(tr, 60.0, [], None, meta={"title": "t", "uploader": "u"})
    assert "LOOP ALAMI" in p and "JANGAN DIPAKSA" in p
    assert "BRIDGE" in p and "CLIFFHANGER" in p
    assert '"loop": false' in p and '"loop_note"' in p
    assert "OTAK SNOOPY v8" in p


def test_clip_meta_carries_loop_fields():
    """Field loop ikut sampai metadata klip (UI/API) — terlihat & terpakai."""
    from backend import pipeline
    m = {"start": 1.0, "end": 30.0, "title": "loop", "hook": "h", "score": 9,
         "loop": True, "loop_note": "bridge: 'dan kamu tak akan percaya'"}
    meta = pipeline._clip_meta("clip_01", m, 720, 1280, {"id": "vid"})
    assert meta["loop"] is True
    assert "tak akan percaya" in meta["loop_note"]
