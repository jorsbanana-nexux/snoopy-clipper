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


def test_cookie_opts_falls_back_to_cookiefile_once_browser_broken(monkeypatch, tmp_path):
    """Bug lama: begitu _cookies_broken=True, _cookie_opts() balikin {} langsung
    -- cookies.txt yang sudah ditaruh user TIDAK PERNAH dilihat lagi. Sekarang
    harus tetap jatuh ke cookies.txt kalau filenya ada."""
    cf = tmp_path / "cookies.txt"
    cf.write_text("# Netscape HTTP Cookie File\n")
    monkeypatch.setattr(downloader.config, "COOKIES_FILE", str(cf))
    monkeypatch.setattr(downloader.config, "COOKIES_FROM_BROWSER", "chrome")
    monkeypatch.setattr(downloader, "_cookies_broken", True)   # browser sudah terbukti rusak
    opts = downloader._cookie_opts()
    assert opts == {"cookiefile": str(cf)}


def test_cookie_opts_no_cookiefile_when_broken_and_no_file(monkeypatch, tmp_path):
    monkeypatch.setattr(downloader.config, "COOKIES_FILE", str(tmp_path / "tidak_ada.txt"))
    monkeypatch.setattr(downloader.config, "COOKIES_FROM_BROWSER", "chrome")
    monkeypatch.setattr(downloader, "_cookies_broken", True)
    assert downloader._cookie_opts() == {}


def test_extract_falls_back_to_cookiefile_before_giving_up_bare(monkeypatch, tmp_path):
    """Skenario nyata: COOKIES_FROM_BROWSER=chrome gagal (Chrome App-Bound
    Encryption / terkunci OS) TAPI user sudah punya cookies.txt -> video yang
    butuh login (age-restricted dsb) tetap harus lolos lewat cookies.txt,
    BUKAN langsung dianggap 'tidak tersedia' tanpa cookie sama sekali."""
    monkeypatch.setattr(downloader, "_cookies_broken", False)
    cf = tmp_path / "cookies.txt"
    cf.write_text("# Netscape HTTP Cookie File\n")
    monkeypatch.setattr(downloader.config, "COOKIES_FILE", str(cf))
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
            if self.opts.get("cookiefile"):
                return {"id": "ok-via-cookiefile"}
            raise yt_dlp.utils.DownloadError("ERROR: [youtube] x: This video is not available")

    monkeypatch.setattr(yt_dlp, "YoutubeDL", FakeYDL)
    info = downloader._extract({"cookiesfrombrowser": ("chrome",)}, "https://x", download=False)
    assert info["id"] == "ok-via-cookiefile"
    assert len(calls) == 2
    assert calls[1]["cookiefile"] == str(cf)


def test_extract_falls_back_to_bare_when_cookiefile_also_fails(monkeypatch, tmp_path):
    monkeypatch.setattr(downloader, "_cookies_broken", False)
    cf = tmp_path / "cookies.txt"
    cf.write_text("# Netscape HTTP Cookie File\n")
    monkeypatch.setattr(downloader.config, "COOKIES_FILE", str(cf))
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
                raise yt_dlp.utils.DownloadError("ERROR: Could not copy Chrome cookie database.")
            if self.opts.get("cookiefile"):
                raise yt_dlp.utils.DownloadError("ERROR: cookies.txt expired/invalid cookie")
            return {"id": "ok-bare"}

    monkeypatch.setattr(yt_dlp, "YoutubeDL", FakeYDL)
    info = downloader._extract({"cookiesfrombrowser": ("chrome",)}, "https://x", download=False)
    assert info["id"] == "ok-bare"
    assert len(calls) == 3
