"""Kontrak: gagal baca cookie browser (Chrome dikunci OS, dsb) tidak boleh
menggagalkan seluruh job kalau videonya publik — retry otomatis tanpa cookie."""
import yt_dlp

from backend import downloader


def test_cookie_browser_failure_falls_back_and_remembers(monkeypatch):
    monkeypatch.setattr(downloader, "_cookies_broken", False)
    calls = []

    class FakeYDL:
        def __init__(self, opts):
            self.opts = opts
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
        def extract_info(self, url, download=False):
            calls.append(dict(self.opts))
            if self.opts.get("cookiesfrombrowser"):
                raise yt_dlp.utils.DownloadError(
                    "ERROR: Could not copy Chrome cookie database. See "
                    "https://github.com/yt-dlp/yt-dlp/issues/7271 for more info")
            return {"id": "ok", "title": "T", "duration": 10.0}

    monkeypatch.setattr(yt_dlp, "YoutubeDL", FakeYDL)

    info = downloader._extract({"cookiesfrombrowser": ("chrome",)}, "https://x", download=False)
    assert info["id"] == "ok"
    assert len(calls) == 2                       # gagal 1x (dgn cookie) -> sukses (tanpa cookie)
    assert "cookiesfrombrowser" not in calls[1]
    assert downloader._cookies_broken is True     # diingat untuk panggilan berikutnya

    # panggilan KEDUA: _cookie_opts() sudah tahu cookie rusak -> opts tanpa
    # cookiesfrombrowser dari awal -> _extract cuma jalan 1x, tidak retry
    calls.clear()
    monkeypatch.setattr(downloader.config, "COOKIES_FROM_BROWSER", "chrome")
    opts2 = downloader._cookie_opts()
    assert "cookiesfrombrowser" not in opts2
    info2 = downloader._extract(opts2, "https://y", download=False)
    assert info2["id"] == "ok"
    assert len(calls) == 1


def test_non_cookie_download_error_still_raises(monkeypatch):
    """Error DownloadError lain (video privat/dihapus) TETAP harus gagal — bukan ditelan."""
    monkeypatch.setattr(downloader, "_cookies_broken", False)

    class FakeYDL:
        def __init__(self, opts):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
        def extract_info(self, url, download=False):
            raise yt_dlp.utils.DownloadError("ERROR: Video unavailable")

    monkeypatch.setattr(yt_dlp, "YoutubeDL", FakeYDL)
    import pytest
    with pytest.raises(yt_dlp.utils.DownloadError, match="unavailable"):
        downloader._extract({"cookiesfrombrowser": ("chrome",)}, "https://z", download=False)
