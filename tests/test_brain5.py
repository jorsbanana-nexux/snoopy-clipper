"""5 OTAK SPESIALIS: ruang kerja per-tugas (kunci sendiri, paralel, fallback
model tetap utuh). Kontrak: BRAIN_KEYS kosong = mode 1-otak IDENTIK lama;
kegagalan satu otak tak pernah merusak kurasi kurator."""
from backend import brain, config


def test_role_key_round_robin_dan_kunci_sakit(monkeypatch):
    monkeypatch.setattr(config, "BRAIN_KEYS",
                        ["k1", "k2", "k3", "k4", "k5"])
    assert brain._role_key("kurator") == "k1"
    assert brain._role_key("verifikator") == "k2"
    assert brain._role_key("direktur") == "k4"
    brain._key_health.clear()
    brain._key_health["k2"] = True
    assert brain._role_key("verifikator") == "k3"   # kunci sakit -> tetangga
    brain._key_health.clear()
    monkeypatch.setattr(config, "GEMINI_API_KEY", "kunci-legacy")
    monkeypatch.setattr(config, "BRAIN_KEYS", [])
    assert brain._role_key("kurator") == "kunci-legacy"  # mode 1-otak lama


def test_multi_mode_gerbang(monkeypatch):
    monkeypatch.setattr(config, "BRAIN_KEYS", ["a", "b"])
    assert brain._multi_mode() is True
    monkeypatch.setattr(config, "BRAIN_KEYS", ["a"])
    assert brain._multi_mode() is False
    monkeypatch.setattr(config, "BRAIN_KEYS", [])
    assert brain._multi_mode() is False
    monkeypatch.setattr(config, "BRAIN_MODE", "off")
    monkeypatch.setattr(config, "BRAIN_KEYS", ["a", "b"])
    assert brain._multi_mode() is False              # paksa 1-otak
    monkeypatch.setattr(config, "BRAIN_MODE", "auto")
    monkeypatch.setattr(config, "BRAIN_MODE", "multi")
    monkeypatch.setattr(config, "BRAIN_KEYS", ["a"])
    assert brain._multi_mode() is True              # paksa multi


def test_find_moments_legacy_satu_otak_identik(monkeypatch):
    monkeypatch.setattr(config, "BRAIN_KEYS", [])
    monkeypatch.setattr(config, "GEMINI_API_KEY", "kunci-tunggal")
    calls = []

    def fake_ask(role, prompt, frames=None):
        calls.append(role)
        assert role == "kurator"                     # TAK ada spesialis
        return {"analysis": "x",
                "moments": [{"start": 1.0, "end": 30.0, "title": "tes",
                            "score": 9}]}

    monkeypatch.setattr(brain, "_ask_role", fake_ask)
    tr = {"words": [], "language": "id",
          "lines": [{"start": 0.0, "end": 2.0, "text": "tes"}]}
    out = brain.find_moments(tr, 60.0, None, None, meta={"title": "t"})
    assert calls == ["kurator"]
    assert len(out) == 1 and out[0]["title"] == "tes"


def test_find_moments_lima_otak_paralel_dan_merge(monkeypatch):
    monkeypatch.setattr(config, "BRAIN_KEYS",
                        ["k1", "k2", "k3", "k4", "k5"])
    calls = []

    def fake_ask(role, prompt, frames=None):
        calls.append(role)
        if role == "kurator":
            return {"moments": [
                {"start": 1.0, "end": 20.0, "title": "A", "hook": "h",
                 "score": 8},
                {"start": 30.0, "end": 60.0, "title": "B", "hook": "h2",
                 "score": 7}]}
        if role == "verifikator":
            return {"verdicts": [
                {"i": 0, "keep": True, "score": 9,
                 "hook_improved": "hook verifikator", "start_fix": 0,
                 "end_fix": 0},
                {"i": 1, "keep": False, "score": 3}]}   # B datar -> TOLAK
        if role == "penulis":
            return {"rewrites": [
                {"i": 0, "title": "Judul Poles Memikat",
                 "hook": "hook penulis"}]}
        if role == "direktur":
            return {"directions": [
                {"i": 0, "layout": "duo", "layout_events": [],
                 "topic_tag": "finance", "bgm_mood": "chill"}]}
        raise RuntimeError("tak boleh ada peran lain")

    monkeypatch.setattr(brain, "_ask_role", fake_ask)
    tr = {"words": [], "language": "id",
          "lines": [{"start": 0.0, "end": 2.0, "text": "tes"}]}
    out = brain.find_moments(tr, 120.0, None, None, meta={"title": "t"})
    assert set(calls) == {"kurator", "verifikator", "penulis", "direktur"}
    assert len(out) == 1                                # B dibuang verifikator
    m = out[0]
    assert m["title"] == "Judul Poles Memikat"          # penulis menimpa
    assert m["hook"] == "hook penulis"
    assert m["score"] == 9 and m["layout"] == "duo"     # verifikator + direktur
    assert m["topic_tag"] == "finance" and m["bgm_mood"] == "chill"


def test_spesialis_mati_semua_kurasi_tetap_utuh(monkeypatch):
    """Verifikator/penulis/direktur MATI TOTAL -> momen kurator lolos apa
    adanya — pipeline TIDAK PERNAH gagal karena spesialis."""
    monkeypatch.setattr(config, "BRAIN_KEYS", ["k1", "k2", "k3"])

    def boom(role, prompt, frames=None):
        if role != "kurator":
            raise RuntimeError("otak mati")
        return {"moments": [{"start": 1.0, "end": 30.0, "title": "asli",
                            "score": 9}]}

    monkeypatch.setattr(brain, "_ask_role", boom)
    tr = {"words": [], "language": "id",
          "lines": [{"start": 0.0, "end": 2.0, "text": "tes"}]}
    out = brain.find_moments(tr, 60.0, None, None, meta={"title": "t"})
    assert len(out) == 1 and out[0]["title"] == "asli"


def test_verifikator_score_bawah_floor_tetap_dibuang(monkeypatch):
    """Verifikator keep=true tapi skor jujur rendah -> _validate floor
    membuangnya (gerbang ganda, tak bisa direkayasa lolos)."""
    monkeypatch.setattr(config, "BRAIN_KEYS", ["k1", "k2"])

    def fake_ask(role, prompt, frames=None):
        if role == "kurator":
            return {"moments": [{"start": 1.0, "end": 30.0, "title": "x",
                                 "score": 8}]}
        if role == "verifikator":
            return {"verdicts": [{"i": 0, "keep": True, "score": 4}]}
        return {}

    monkeypatch.setattr(brain, "_ask_role", fake_ask)
    tr = {"words": [], "language": "id",
          "lines": [{"start": 0.0, "end": 2.0, "text": "tes"}]}
    out = brain.find_moments(tr, 60.0, None, None, meta={"title": "t"})
    assert out == []                                     # floor 6 menolak
