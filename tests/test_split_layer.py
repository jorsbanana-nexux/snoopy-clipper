"""Subtitle v3.1: presisi kata + micro-lead + SPLIT LAYER duo (single<->duo).
Kontrak terpenting: layout single/tanpa field -> byte-identik dgn perilaku
normal (frame biasa TIDAK tersentuh)."""
import pytest

from backend import brain, config, pipeline, subtitles


def _words(texts=("dua", "belah", "layar", "atas", "bawah"), step=0.5):
    return [{"start": i * step, "end": i * step + 0.4, "text": t}
            for i, t in enumerate(texts)]


def test_size_naik_3_persen():
    # 0.048 -> 0.0494 = +3% (tanpa .env override)
    assert config.SUBTITLE_SIZE_FRAC == pytest.approx(0.0494, rel=1e-6)


def test_pop_presisi_ms_dan_micro_lead():
    # kata ke-2 mulai 1.6s, klip mulai 0.5s, event mulai 0.5s
    # -> relatif 0.6s = 600ms, dikurangi micro-lead 25ms = 575 (PRESISI, bukan
    # pembulatan 10ms kasar yang dulu menghasilkan 600)
    words = [{"start": 1.0, "end": 1.4, "text": "kata"},
             {"start": 1.6, "end": 2.0, "text": "kedua"}]
    ass = subtitles.build_ass(words, None, None, 1080, 1920, 0.5, 4.0)
    assert "\\t(575," in ass
    assert "\\t(600," not in ass or "\\t(575," in ass  # micro-lead aktif


def test_bounce_tuntas_sebelum_kata_berikutnya():
    # pop_ms=80 -> settle normal 575+160+40=775, tapi kata ke-2... kata ke-2
    # sendiri TIDAK dibatasi; kata ke-1 (fade 0) dibatasi kata ke-2 (575):
    # settle_end = min(0+200, 575) = 200 -> \t(80,200
    words = [{"start": 0.0, "end": 0.4, "text": "pertama"},
             {"start": 0.6, "end": 1.0, "text": "kedua"}]
    ass = subtitles.build_ass(words, None, None, 1080, 1920, 0.0, 3.0)
    assert "\\t(80,200," in ass


def test_duo_dua_posisi_dan_teks_ganda():
    ass = subtitles.build_ass(_words(), None, None, 1080, 1920, 0.0, 4.0,
                              layout="duo")
    assert "\\pos(540,480)" in ass     # tengah belahan ATAS (25%)
    assert "\\pos(540,1440)" in ass    # tengah belahan BAWAH (75%)
    n_atas = ass.count("\\pos(540,480)")
    n_bawah = ass.count("\\pos(540,1440)")
    assert n_atas == n_bawah >= 1
    # teks yang sama muncul DI KEDUA belahan (sinkron)
    assert ass.count("Atas") == 2 and ass.count("Bawah") == 2


def test_single_identik_dengan_tanpa_field():
    a = subtitles.build_ass(_words(), None, None, 1080, 1920, 0.0, 4.0)
    b = subtitles.build_ass(_words(), None, None, 1080, 1920, 0.0, 4.0,
                            layout="single", layout_events=[])
    assert a == b                          # frame normal tak tersentuh
    assert "\\pos(540,480)" not in a       # tak ada jejak duo


def test_transisi_duo_ke_single_crossfade():
    words = [{"start": i * 0.6, "end": 0.4 + i * 0.6, "text": t}
             for i, t in enumerate(["satu", "dua", "tiga", "empat", "lima", "enam"])]
    ass = subtitles.build_ass(words, None, None, 1080, 1920, 0.0, 4.0,
                              layout="duo",
                              layout_events=[{"t": 1.8, "layout": "single"}])
    assert "\\fad(0,120)" in ass   # segmen duo memudar di perbatasan
    assert "\\fad(120," in ass    # segmen single muncul dengan fade-in


def test_layout_switch_dimatikan(monkeypatch):
    monkeypatch.setattr(config, "SUBTITLE_SPLIT_LAYER", False)
    ass = subtitles.build_ass(_words(), None, None, 1080, 1920, 0.0, 4.0,
                              layout="duo",
                              layout_events=[{"t": 1.0, "layout": "single"}])
    assert "\\pos(540,480)" not in ass   # rollback instan via .env


def test_anti_flicker_dan_validasi_events():
    words = _words(("kata",) * 6)
    ass = subtitles.build_ass(words, None, None, 1080, 1920, 0.0, 4.0,
                              layout="single",
                              layout_events=[{"t": 0.1, "layout": "duo"},
                                              {"t": 0.3, "layout": "single"}])
    # gonta-ganti < 0.4s dan terlalu mepet tepi -> diabaikan, tetap single
    assert "\\pos(540,480)" not in ass


def test_prompt_direktur_duo_tegas_dan_multi_orang():
    """Spec owner 2026-09-12: duo WAJIB saat dua zona sama-sama penting
    (podcast/gameplay dsb), tiap zona boleh BANYAK orang; ragu -> single."""
    dp = brain._D_PROMPT
    assert "duo WAJIB" in dp
    assert "BANYAK orang" in dp


def test_prompt_dan_validate_otak(monkeypatch):
    monkeypatch.setattr(config, "MIN_CLIP_SEC", 15.0)  # fokus layout, bukan durasi
    tr = {"lines": [{"start": 0.0, "end": 2.0, "text": "tes"}], "language": "id"}
    p = brain._build_prompt(tr, 60.0, [], None, meta={"title": "t", "uploader": "u"})
    assert '"layout": "single"' in p and "layout_events" in p
    assert "SPLIT LAYER" in p and "JANGAN pakai duo" in p
    moments = [{"start": 1.0, "end": 30.0, "title": "x", "score": 9,
                "layout": "duo",
                "layout_events": [{"t": 10.0, "layout": "single"},
                                  {"t": 99.0, "layout": "duo"},
                                  {"t": 5.0, "layout": "duo"}]}]
    out = brain._validate(moments, [], 120.0)
    assert out[0]["layout"] == "duo"
    # t=99 di luar klip dibuang; sisanya urut & sah
    assert out[0]["layout_events"] == [{"t": 5.0, "layout": "duo"},
                                       {"t": 10.0, "layout": "single"}]


def test_meta_klip_membawa_layout():
    m = {"start": 1.0, "end": 30.0, "title": "podcast gameplay", "score": 9,
         "layout": "duo"}
    meta = pipeline._clip_meta("clip_01", m, 720, 1280, {"id": "vid"})
    assert meta["layout"] == "duo"
