"""Kontrak track transkrip (bug nyata 2026-09-11): video English yang diucap
English keluar klip FULL INDONESIA — _LANG_PRIORITY ['id',...] memilih
auto-terjemahan 'id' padahal track asli 'en-orig' tersedia. Track asli
(dengan suffix -orig) WAJIB menang atas auto-terjemahan."""


def _track(fmts=None):
    return fmts or [{"ext": "json3"}]


def test_video_english_pilih_track_asli_bukan_terjemahan():
    from backend import captions
    info = {"subtitles": {}, "automatic_captions": {
        "id": _track(), "en-orig": _track()}}
    lang, _ = captions._pick_caption(info)
    assert lang == "en-orig"      # bahasa yang DIUCAPKAN, bukan terjemahan mesin


def test_video_indonesia_tetap_indonesia():
    from backend import captions
    info = {"subtitles": {}, "automatic_captions": {
        "en": _track(), "id-orig": _track()}}
    lang, _ = captions._pick_caption(info)
    assert lang == "id-orig"


def test_manual_pembuat_tetap_menang():
    from backend import captions
    info = {"subtitles": {"id": _track()},
            "automatic_captions": {"en-orig": _track()}}
    lang, _ = captions._pick_caption(info)
    assert lang == "id"


def test_auto_tanpa_orig_fallback_prioritas():
    from backend import captions
    info = {"subtitles": {}, "automatic_captions": {"en": _track(), "de": _track()}}
    lang, _ = captions._pick_caption(info)
    assert lang == "en"


def test_tanpa_track_sama_sekali():
    from backend import captions
    lang, fmts = captions._pick_caption({"subtitles": {},
                                         "automatic_captions": {}})
    assert lang is None and fmts is None
