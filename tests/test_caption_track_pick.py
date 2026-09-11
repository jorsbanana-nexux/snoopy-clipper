"""Kontrak track transkrip (bug nyata 2026-09-11, dua klip full Indonesia utk
video English): bahasa yang DIUCAPKAN (info['language']) WAJIB menang atas
segalanya — termasuk sub MANUAL 'id' yang diunggah channel Indonesia, dan
auto-terjemahan 'id' prioritas pertama."""


def _track():
    return [{"ext": "json3"}]


def test_spoken_language_menang_atas_manual_terjemahan():
    """Reproduksi EKSAK data nyata: video English (language='en') milik channel
    Indonesia yang mengunggah sub manual 'id' — klip WAJIB English."""
    from backend import captions
    info = {"language": "en",
            "subtitles": {"id": _track(), "ar": _track()},
            "automatic_captions": {"id": _track(), "en-orig": _track(), "en": _track()}}
    lang, _ = captions._pick_caption(info)
    assert lang == "en"


def test_video_english_tanpa_manual_pilih_en_orig_bukan_terjemahan():
    from backend import captions
    info = {"language": "en", "subtitles": {},
            "automatic_captions": {"id": _track(), "en-orig": _track()}}
    lang, _ = captions._pick_caption(info)
    assert lang == "en-orig"      # bahasa asli, bukan terjemahan mesin


def test_video_indonesia_tetap_indonesia():
    from backend import captions
    info = {"language": "id", "subtitles": {},
            "automatic_captions": {"en": _track(), "id-orig": _track()}}
    lang, _ = captions._pick_caption(info)
    assert lang == "id-orig"


def test_tanpa_info_language_manual_prioritas_lama():
    """Platform tanya 'language' (yt-dlp lain): perilaku lama tetap aman."""
    from backend import captions
    info = {"subtitles": {"id": _track()},
            "automatic_captions": {"en-orig": _track()}}
    lang, _ = captions._pick_caption(info)
    assert lang == "id"


def test_tanpa_info_language_auto_orig_menang():
    from backend import captions
    info = {"subtitles": {}, "automatic_captions": {"id": _track(), "en-orig": _track()}}
    lang, _ = captions._pick_caption(info)
    assert lang == "en-orig"


def test_tanpa_track_sama_sekali():
    from backend import captions
    lang, fmts = captions._pick_caption({"subtitles": {}, "automatic_captions": {}})
    assert lang is None and fmts is None
