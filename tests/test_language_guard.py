"""Kontrak BAHASA (rancangan awal, wajib): SEMUA teks klip — judul (= teks
thumbnail), hook, deskripsi YouTube — mengikuti bahasa yang DIUCAPKAN di video.
Penjaga deterministik: teks molor -> SATU panggilan poles 'penulis' (timestamp/
skor tak tersentuh); teks sudah benar -> nol biaya tambahan.
Latar: uji nyata 2026-09-11 — model fallback 503 menulis judul Bahasa
Indonesia untuk video English; kontrak di prompt ternyata probabilistik."""
import pytest

from backend import brain, config


@pytest.fixture(autouse=True)
def _durasi_min_lama(monkeypatch):
    """Default produksi MIN_CLIP_SEC kini 60 dtk (owner 2026-09-12). Test di
    file ini memakai klip pendek (fokus ke logika lain) -> kembalikan 15."""
    monkeypatch.setattr(config, "MIN_CLIP_SEC", 15.0)



def _transcript(lang="en"):
    return {"language": lang,
            "lines": [{"start": 0, "end": 20, "text": "hello world"}],
            "words": [{"start": 0, "end": 5, "text": "hello"},
                      {"start": 5, "end": 20, "text": "world"}]}


def _setup(monkeypatch, kurator_moments, fix_reply=None):
    monkeypatch.setattr(config, "GEMINI_API_KEY", "test")
    monkeypatch.setattr(config, "BRAIN_KEYS", [])       # mode 1-otak murni
    monkeypatch.setattr(config, "BRAIN_MODE", "auto")
    calls = []

    def fake_ask(role, prompt, frames=None):
        calls.append(role)
        if role == "kurator":
            return {"analysis": "ok", "moments": kurator_moments}
        return fix_reply if fix_reply is not None else []

    monkeypatch.setattr(brain, "_ask_role", fake_ask)
    return calls


def _moment(title, hook="Ternyata rahasia ini ada", desc="Deskripsi tentang manusia"):
    return {"start": 0, "end": 18, "title": title, "hook": hook, "score": 9,
            "yt_description": desc, "bgm_mood": "upbeat"}


def test_video_english_judul_indonesia_dipoles(monkeypatch):
    """Video English + judul Indonesia -> poles 1x, teks jadi English,
    timestamp/skor tak tersentuh."""
    calls = _setup(monkeypatch, [_moment("Rahasia Besar Tentang Manusia")],
                   fix_reply=[{"i": 0, "title": "The Big Secret About Humanity",
                               "hook": "Turns out this secret is real",
                               "yt_description": "The secret about us all"}])
    out = brain.find_moments(_transcript("en"), 20.0)
    assert calls == ["kurator", "penulis"]
    assert out[0]["title"] == "The Big Secret About Humanity"
    assert out[0]["hook"] == "Turns out this secret is real"
    assert (out[0]["start"], out[0]["score"]) == (0, 9)
    assert out[0]["end"] in (18, 20)   # snap ke batas kata (fitur)


def test_teks_sudah_benar_nol_panggilan_tambahan(monkeypatch):
    """Video English + judul English -> hanya kurator, TANPA poles."""
    calls = _setup(monkeypatch, [_moment("The Big Secret About Humanity",
                                         hook="Turns out it is real",
                                         desc="The secret about us all")])
    out = brain.find_moments(_transcript("en"), 20.0)
    assert calls == ["kurator"]
    assert out[0]["title"] == "The Big Secret About Humanity"


def test_video_indonesia_bebas_polisan(monkeypatch):
    """Video Indonesia: bahasa target = id, penjaga tak pernah memicu poles."""
    calls = _setup(monkeypatch, [_moment("Rahasia Besar Tentang Manusia")])
    out = brain.find_moments(_transcript("id"), 20.0)
    assert calls == ["kurator"]
    assert out[0]["title"] == "Rahasia Besar Tentang Manusia"


def test_video_jepang_wajib_aksara_jepang(monkeypatch):
    """Video Jepang + judul tanpa aksara Jepang -> poles; jawaban aksara
    Jepang diterima apa adanya (ensure_ascii tak merusak)."""
    calls = _setup(monkeypatch, [_moment("Rahasia Besar Tentang Manusia")],
                   fix_reply=[{"i": 0, "title": "人類の大きな秘密を暴く",
                               "hook": "実はこの秘密は本物",
                               "yt_description": "我々全員の秘密"}])
    out = brain.find_moments(_transcript("ja"), 20.0)
    assert calls == ["kurator", "penulis"]
    assert out[0]["title"] == "人類の大きな秘密を暴く"


def test_poles_gagal_klip_tetap_hidup(monkeypatch):
    """Poles error (mis. 503) -> klip tetap keluar dengan teks lama."""
    def boom(role, prompt, frames=None):
        if role == "kurator":
            return {"analysis": "ok", "moments": [_moment("Rahasia Besar Manusia")]}
        raise RuntimeError("503")
    monkeypatch.setattr(config, "GEMINI_API_KEY", "test")
    monkeypatch.setattr(config, "BRAIN_KEYS", [])
    monkeypatch.setattr(brain, "_ask_role", boom)
    out = brain.find_moments(_transcript("en"), 20.0)
    assert out and out[0]["title"] == "Rahasia Besar Manusia"


@pytest.mark.parametrize("text,lang,ok", [
    ("The Internet Changed Forever", "en", True),
    ("Rahasia Besar Tentang Manusia", "en", False),
    ("yang dan ini tentang", "es", False),
    ("Los secretos del universo", "es", True),
    ("人類の秘密", "ja", True),
    ("큰 비밀", "ko", True),
    ("rahasia manusia", "ko", False),
    ("أسرار البشرية", "ar", True),
    ("ความลับ", "th", True),
    ("Секреты", "ru", True),
    ("apa pun", "id", True),
])
def test_heuristik_bahasa(text, lang, ok):
    assert brain._text_ok(text, lang) is ok


def test_lang_display_menyebut_nama_bahasa():
    d = brain._lang_display("en")
    assert "English" in d and "WAJIB" in d
    assert "Bahasa Indonesia" in brain._lang_display("id")
    assert "—" in brain._lang_display("")
