"""Kontrak durasi minimal klip (permintaan owner 2026-09-12):
- klip MINIMAL 60 detik, boleh lebih (prompt meminta rentang min-max)
- klip di bawah 54 dtk (toleransi snap ±2 dtk per sisi) DIBUANG
- kalimat terakhir klip WAJIB penutup — prompt melarang end menjalar/bablas
"""
from backend import brain, config


def test_default_minimal_60_detik():
    assert config.MIN_CLIP_SEC == 60.0


def test_prompt_meminta_rentang_60_hingga_max():
    tr = {"language": "id", "words": [],
          "lines": [{"start": 0.0, "end": 2.0, "text": "tes"}]}
    p = brain._build_prompt(tr, 100.0, None, 0)
    assert f"{int(config.MIN_CLIP_SEC)}-{int(config.MAX_CLIP_SEC)} detik" in p


def test_klip_bawah_floor_54_dibuang_yang_layak_tetap():
    out = brain._validate(
        [{"start": 0.0, "end": 40.0, "title": "pendek", "score": 9},
         {"start": 0.0, "end": 58.0, "title": "layak", "score": 9}],
        [], 100.0)
    assert [m["title"] for m in out] == ["layak"]


def test_prompt_aturan_penutup_anti_bablas():
    """Otak dilarang buta akhir: end TIDAK BOLEH menjalar lewat penutup —
    subtitle berhenti di penutup, bukan bablas ke sisa video."""
    tr = {"language": "id", "words": [],
          "lines": [{"start": 0.0, "end": 2.0, "text": "tes"}]}
    p = brain._build_prompt(tr, 100.0, None, 0)
    assert "PENUTUP" in p and "menjalar" in p and "bablas" in p
    assert "MENJALAR" in brain._V_PROMPT  # verifikator memotong ekor bablas
