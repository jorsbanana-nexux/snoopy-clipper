"""Fallback transkrip platform: error network TIDAK boleh menjatuhkan job.

429 (rate-limit YouTube, sementara) atau network mati saat ambil metadata /
file transkrip -> fetch() = None -> pipeline otomatis lanjut ke jalur whisper.
Kunci: jalur normal caption-only TETAP hidup.
"""
import io
from unittest.mock import patch

from backend import captions

_URL = "https://youtube.com/watch?v=aaaaaaaaaaa"
_FAKE_INFO = {"subtitles": {}, "automatic_captions": {
    "id": [{"ext": "json3", "url": "https://example.com/cap.json3"}]}}
_GOOD_JSON3 = (b'{"events":[{"tStartMs":0,"dDurationMs":1000,'
               b'"segs":[{"utf8":"halo"}]}]}')


def test_metadata_429_fallback_whisper():
    """429 saat extract_info -> None (fallback whisper), BUKAN exception."""
    with patch.object(captions.yt_dlp.YoutubeDL, "extract_info",
                      side_effect=Exception("HTTP Error 429: Too Many Requests")):
        assert captions.fetch(_URL) is None


def test_unduh_429_fallback_whisper():
    """Metadata sukses tapi unduh file transkrip kena 429 -> None, bukan crash."""
    with patch.object(captions.yt_dlp.YoutubeDL, "extract_info",
                      return_value=_FAKE_INFO), \
         patch.object(captions.urllib.request, "urlopen",
                      side_effect=Exception("HTTP Error 429: Too Many Requests")):
        assert captions.fetch(_URL) is None


def test_jalur_normal_tetap_hidup():
    """Transkrip terunduh normal -> hasil terparse (jalur cepat tak mati)."""
    with patch.object(captions.yt_dlp.YoutubeDL, "extract_info",
                      return_value=_FAKE_INFO), \
         patch.object(captions.urllib.request, "urlopen",
                      return_value=io.BytesIO(_GOOD_JSON3)):
        r = captions.fetch(_URL)
    assert r is not None
    assert r["language"] == "id"
    assert r["lines"][0]["text"] == "halo"
