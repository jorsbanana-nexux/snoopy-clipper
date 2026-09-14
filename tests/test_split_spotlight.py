"""SPLIT LAYER v3 — SPOTLIGHT duo (menyorot pembicara aktif, bergantian
mulus) + GERBANG ANAK (konten anak TIDAK PERNAH split, apapun kata otak).

Kontrak:
- duo TANPA duo_zones / speaker tak dikenal -> byte-identik dgn duo klasik
  (dua belahan sama terang) — perilaku lama tak tersentuh.
- duo + duo_zones + kata berlabel -> zona pembicara aktif TERANG (&H00&),
  zona satunya meredup (&H60&) — bergantian per frasa (adegan ramai).
- single -> zones diabaikan sama sekali.
"""
import pytest

from backend import brain as B, config, subtitles


def _w(text, s, speaker=None):
    d = {"start": s, "end": s + 0.4, "text": text}
    if speaker:
        d["speaker"] = speaker
    return d


def _duo_ass(words, zones=None, layout="duo"):
    return subtitles.build_ass(words, None, None, 1080, 1920, 0.0, 8.0,
                               layout=layout, layout_events=[],
                               duo_zones=zones)


def _events(ass):
    return [ln for ln in ass.splitlines() if ln.startswith("Dialogue:")]


def test_spotlight_zona_aktif_terang_lainnya_redup():
    # SPEAKER_00 (zona atas) bicara -> ATAS &H00&, BAWAH &H60& (meredup)
    words = [_w("saya", 0.2, "SPEAKER_00"), _w("atas", 0.7, "SPEAKER_00"),
             _w("sendiri", 1.2, "SPEAKER_00")]
    zones = {"atas": "SPEAKER_00", "bawah": "SPEAKER_01"}
    ass = _duo_ass(words, zones)
    atas = [e for e in _events(ass) if "\\pos(540,480)" in e]
    bawah = [e for e in _events(ass) if "\\pos(540,1440)" in e]
    assert atas and bawah
    assert any("\\alpha&H60&" in e for e in bawah)   # zona diam meredup
    assert all("\\alpha&H60&" not in e for e in atas)  # zona aktif terang
    # teks tetap SAMA di kedua belahan (dobel, sinkron)
    assert sum(e.count("Atas") for e in atas + bawah) == 2


def test_spotlight_bergantian_mulus_antar_frasa():
    # adegan ramai: pembicara bertukar tiap frasa -> sorotan ikut pindah
    words = [_w("kata", i * 0.6, "SPEAKER_%02d" % (i % 2)) for i in range(6)]
    zones = {"atas": "SPEAKER_00", "bawah": "SPEAKER_01"}
    ass = _duo_ass(words, zones)
    atas_dim = [e for e in _events(ass)
                if "\\pos(540,480)" in e and "\\alpha&H60&" in e]
    bawah_dim = [e for e in _events(ass)
                 if "\\pos(540,1440)" in e and "\\alpha&H60&" in e]
    atas_full = [e for e in _events(ass)
                 if "\\pos(540,480)" in e and "\\alpha&H60&" not in e]
    bawah_full = [e for e in _events(ass)
                  if "\\pos(540,1440)" in e and "\\alpha&H60&" not in e]
    # kedua belahan pernah jadi sorotan & pernah meredup = bergantian
    assert atas_full and bawah_full
    assert atas_dim and bawah_dim


def test_duo_tanpa_label_pembicara_identik_duo_klasik():
    words = [_w("dua", 0.2), _w("belah", 0.7), _w("layar", 1.2)]
    klasik = _duo_ass(words)
    # zones ada tapi kata tak berlabel -> fallback dua-duanya terang
    spot = _duo_ass(words, {"atas": "SPEAKER_00", "bawah": "SPEAKER_01"})
    assert klasik == spot
    assert "\\alpha&H60&" not in spot


def test_duo_zones_tak_dikenal_pembicara_fallback_terang():
    # pembicara berlabel tapi TIDAK ada di mapping -> dua-duanya terang
    words = [_w("aku", 0.2, "SPEAKER_99"), _w("bawah", 0.7, "SPEAKER_99")]
    ass = _duo_ass(words, {"atas": "SPEAKER_00", "bawah": "SPEAKER_01"})
    assert "\\alpha&H60&" not in ass


def test_single_mengabaikan_duo_zones():
    words = [_w("satu", 0.2, "SPEAKER_00"), _w("layar", 0.7, "SPEAKER_00")]
    a = _duo_ass(words, {"atas": "SPEAKER_00", "bawah": "SPEAKER_01"},
                 layout="single")
    b = subtitles.build_ass(words, None, None, 1080, 1920, 0.0, 8.0)
    assert a == b
    assert "\\pos(540,480)" not in a


def test_kill_switch_duo_spotlight(monkeypatch):
    monkeypatch.setattr(config, "SUBTITLE_DUO_SPOTLIGHT", False)
    words = [_w("aku", 0.2, "SPEAKER_00"), _w("atas", 0.7, "SPEAKER_00")]
    ass = _duo_ass(words, {"atas": "SPEAKER_00", "bawah": "SPEAKER_01"})
    assert "\\alpha&H60&" not in ass   # kembali duo klasik: sama terang


# ---------------- otak: validasi duo_zones + gerbang anak ----------------

def test_brain_duo_zones_validasi_keras():
    f = B._duo_zones
    assert f({"atas": "SPEAKER_00", "bawah": "SPEAKER_01"}) == \
        {"atas": "SPEAKER_00", "bawah": "SPEAKER_01"}
    assert f({"atas": "A", "bawah": "A"}) == {}            # sama -> tolak
    assert f({"atas": "", "bawah": "B"}) == {}             # kosong -> tolak
    assert f({"atas": "A"}) == {}                           # kurang -> tolak
    assert f(None) == {} and f("aneh") == {} and f([1]) == {}
    assert f({"top": "A", "bottom": "B"}) == {"atas": "A", "bawah": "B"}
    assert f({"atas": "x" * 40, "bawah": "B"}) == {"atas": "x" * 24, "bawah": "B"}


def test_brain_validate_menyimpan_duo_zones():
    # klip minimal 60 dtk (config) -> rentang kata & klip harus panjang
    words = [_w("kata", 0.2 + i * 0.6) for i in range(130)]
    m = [{"start": 0.2, "end": 65.0, "title": "T", "score": 9,
          "layout": "duo",
          "duo_zones": {"atas": "SPEAKER_00", "bawah": "SPEAKER_01"}}]
    out = B._validate(m, words, 120.0)
    assert out and out[0]["duo_zones"] == \
        {"atas": "SPEAKER_00", "bawah": "SPEAKER_01"}


def _mk_transcript(speakers=("SPEAKER_00",)):
    words = [_w(f"kata{i}", 0.2 + i * 0.6, speakers[i % len(speakers)])
             for i in range(130)]
    return {"language": "id", "words": words, "lines": []}


def test_brain_gerbang_anak_tanpa_split(monkeypatch):
    """MODE ANAK: apapun kata otak (layout duo + events + zones), semua klip
    dipaksa balik single — video anak TIDAK PERNAH split."""
    raw = {"moments": [
        {"start": 0.4, "end": 65.0, "title": "Lucu Banget", "hook": "h",
         "score": 9, "content_type": "anak", "bgm_mood": "upbeat",
         "layout": "duo",
         "layout_events": [{"t": 3.0, "layout": "duo"}],
         "duo_zones": {"atas": "SPEAKER_00", "bawah": "SPEAKER_01"}},
    ]}
    monkeypatch.setattr(B.config, "GEMINI_API_KEY", "kunci-test")
    monkeypatch.setattr(B, "_ask_role", lambda *a, **k: raw)
    monkeypatch.setattr(B, "_multi_mode", lambda: False)
    monkeypatch.setattr(B, "_enforce_language", lambda ms, lang: ms)
    moments = B.find_moments(_mk_transcript(), 120.0, meta={"is_kids": True})
    assert moments
    for m in moments:
        assert m["layout"] == "single"
        assert m["layout_events"] == [] and m["duo_zones"] == {}


def test_prompt_utama_split_pintar_bukan_semua_video():
    p = B.PROMPT
    assert "TIDAK PERNAH split" in p            # gate anak
    assert "JANGAN DIPAKSA KE SEMUA VIDEO" in p
    assert "duo_zones" in p                     # spotlight multi-pembicara
    assert '"duo_zones": {{}}' in p             # skema JSON diperbarui
    assert 'kembali "single"' in p              # balik single setelah ramai
    # tidak ada lagi duplikasi nomor aturan (dulu 12 & 13 dobel)
    import re as _re
    nums = _re.findall(r"^(\d+)\. ", p, _re.M)
    assert nums == sorted(set(nums), key=int) and len(nums) == len(set(nums)), nums


def test_prompt_direktur_punya_duo_zones_dan_gate_anak():
    dp = B._D_PROMPT
    assert '"duo_zones"' in dp
    assert "TIDAK PERNAH split" in dp
    assert "content_type" in dp    # kandidat direktur kini bawa jenis konten
