"""Kontrak cepat, offline, untuk URL, cache media, dan transkrip platform."""
import json

from backend import captions, downloader


def test_youtube_kids_is_normalized_and_remains_detectable():
    url = "https://www.youtubekids.com/watch?v=abcDEF_123&feature=share"
    assert downloader.normalize_url(url) == "https://www.youtube.com/watch?v=abcDEF_123"
    assert downloader.detect_kids(url, "", "") is True


def test_youtube_profile_home_uses_real_videos_tab():
    assert downloader._youtube_profile_videos_url("https://www.youtube.com/@creator") == (
        "https://www.youtube.com/@creator/videos")
    assert downloader._youtube_profile_videos_url(
        "https://www.youtube.com/channel/UC123/videos?view=0") == (
        "https://www.youtube.com/channel/UC123/videos?view=0")
    assert downloader._youtube_profile_videos_url(
        "https://www.youtube.com/watch?v=abcDEF_123") == "https://www.youtube.com/watch?v=abcDEF_123"


def test_cached_media_accepts_non_mp4_and_prefers_mp4(tmp_path):
    base = tmp_path / "source"
    webm = tmp_path / "source.webm"
    webm.write_bytes(b"x" * 2048)
    assert downloader.cached_media(base) == webm
    mp4 = tmp_path / "source.mp4"
    mp4.write_bytes(b"x" * 2048)
    assert downloader.cached_media(base) == mp4


def test_json3_removes_rolling_caption_overlap():
    raw = json.dumps({"events": [
        {"tStartMs": 0, "dDurationMs": 1000, "segs": [{"utf8": "Halo apa"}]},
        {"tStartMs": 900, "dDurationMs": 1100, "segs": [{"utf8": "Halo apa kabar"}]},
        {"tStartMs": 1900, "dDurationMs": 1200, "segs": [{"utf8": "kabar baik semua"}]},
    ]})
    parsed = captions._parse_json3(raw, "id")
    assert [line["text"] for line in parsed["lines"]] == ["Halo apa", "kabar", "baik semua"]


def test_vtt_accepts_timestamp_without_hour_component():
    raw = "WEBVTT\n\n00:01.250 --> 00:03.500\nHalo dunia\n"
    parsed = captions._parse_vtt(raw, "id")
    assert parsed["lines"] == [{"start": 1.25, "end": 3.5, "text": "Halo dunia"}]


def test_channel_picker_rejects_live_and_returns_playable_url():
    entries = [
        {"title": "Live", "url": "https://example.test/live", "live_status": "is_live"},
        {"title": "Video terbaik", "url": "https://example.test/v", "duration": 600,
         "view_count": 12000},
    ]
    url, title, why = downloader.pick_channel_best(entries)
    assert (url, title) == ("https://example.test/v", "Video terbaik")
    assert "views" in why
