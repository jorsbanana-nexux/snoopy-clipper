"""Kontrak ketahanan URL: satu link apa pun — YouTube (termasuk Kids), TikTok,
Instagram, X, Facebook — tidak boleh mati hanya karena bentuk URL, format
stream, atau cookie browser yang terkunci sesaat.

Semua kejadian nyata dari log owner 2026-09-14.
"""
import pytest
import yt_dlp

from backend import downloader


# ---------- normalisasi URL: semua bentuk link YouTube Kids ----------

@pytest.mark.parametrize("raw", [
    "https://www.youtubekids.com/watch?v=eC9zes6ZZuo",
    "https://youtubekids.com/watch?v=eC9zes6ZZuo",
    "https://kids.youtube.com/watch?v=eC9zes6ZZuo",
    "https://www.youtubekids.com/watch?v=eC9zes6ZZuo&hl=id",
    "https://www.youtubekids.com/watch?hl=id&v=eC9zes6ZZuo",
    "https://m.youtubekids.com/watch?v=eC9zes6ZZuo",
    # bentuk tanpa /watch — dulu lolos begitu saja ke ekstraktor Kids
    "https://youtubekids.com/?v=eC9zes6ZZuo",
    "https://www.youtubekids.com/?video_id=eC9zes6ZZuo",
])
def test_semua_bentuk_url_kids_dinormalkan(raw):
    assert downloader.normalize_url(raw) == "https://www.youtube.com/watch?v=eC9zes6ZZuo"


@pytest.mark.parametrize("raw", [
    "https://www.youtube.com/watch?v=eC9zes6ZZuo",
    "https://youtu.be/eC9zes6ZZuo",
    "https://www.tiktok.com/@user/video/123",
    "https://www.instagram.com/reel/abc/",
    "https://x.com/user/status/123",
])
def test_url_non_kids_tidak_diubah(raw):
    assert downloader.normalize_url(raw) == raw


def test_url_kids_playlist_tidak_dirusak():
    """URL playlist Kids tidak punya video ID tunggal -> biarkan apa adanya."""
    raw = "https://www.youtubekids.com/playlist?list=PL123"
    assert downloader.normalize_url(raw) == raw


def test_url_kosong_aman():
    assert downloader.normalize_url("") == ""
    assert not downloader.normalize_url(None)


# ---------- deteksi lock cookie yang sifatnya sementara ----------

def test_lock_sesaat_terdeteksi():
    inner = PermissionError(13, "Permission denied", "Cookies")
    outer = yt_dlp.utils.DownloadError("ERROR: could not copy Chrome cookie database")
    outer.__cause__ = inner
    assert downloader._is_transient_cookie_lock(outer) is True


def test_kegagalan_cookie_biasa_bukan_lock():
    e = yt_dlp.utils.DownloadError("ERROR: Failed to load cookies")
    assert downloader._is_transient_cookie_lock(e) is False


def test_error_format_terdeteksi():
    assert downloader._is_format_error(
        yt_dlp.utils.DownloadError("ERROR: Requested format is not available"))
    assert not downloader._is_format_error(
        yt_dlp.utils.DownloadError("ERROR: This video is unavailable"))


# ---------- _extract: retry -> cookies.txt -> tanpa cookie ----------

class _FakeYDL:
    """YDL palsu yang meniru Chrome terkunci N kali, lalu sukses."""

    def __init__(self, opts, fail_times=0, always_fail=False):
        self.opts = opts
        self.fail_times = fail_times
        self.always_fail = always_fail

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def extract_info(self, url, download=False):
        if self.always_fail:
            raise yt_dlp.utils.DownloadError(
                "ERROR: [youtube] abc: This video is not available")
        if self.fail_times > 0:
            self.fail_times -= 1
            inner = PermissionError(13, "Permission denied", "Cookies")
            e = yt_dlp.utils.DownloadError("ERROR: could not copy Chrome cookie database")
            e.__cause__ = inner
            raise e
        return {"id": "ok", "title": "T", "duration": 10.0}


def test_cookie_terkunci_sesaat_lolos_setelah_retry(monkeypatch):
    """Chrome baru ditutup -> gagal sekali, retry berhasil, cookie TETAP dipakai."""
    monkeypatch.setattr(downloader, "_cookies_broken", False)
    monkeypatch.setattr(downloader.config, "COOKIE_RETRY", 2)
    monkeypatch.setattr(downloader.config, "COOKIE_RETRY_DELAY", 0.0)
    calls = []
    state = {"n": 1}

    class Y:
        def __init__(self, opts):
            self.opts = opts

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def extract_info(self, url, download=False):
            calls.append(self.opts)
            if state["n"] > 0:
                state["n"] -= 1
                e = yt_dlp.utils.DownloadError("could not copy Chrome cookie database")
                e.__cause__ = PermissionError(13, "Permission denied")
                raise e
            return {"id": "ok"}

    monkeypatch.setattr(yt_dlp, "YoutubeDL", Y)
    info = downloader._extract({"cookiesfrombrowser": ("chrome",)}, "https://x")
    assert info["id"] == "ok"
    assert len(calls) == 2                       # 1 gagal + 1 retry (dengan cookie)
    assert calls[1].get("cookiesfrombrowser") == ("chrome",)
    assert downloader._cookies_broken is False   # cookie TERBUKTI bisa dibaca


def test_cookie_mati_total_jatuh_ke_tanpa_cookie(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(downloader, "_cookies_broken", False)
    monkeypatch.setattr(downloader, "_cookie_warned", False)
    monkeypatch.setattr(downloader.config, "COOKIE_RETRY", 1)
    monkeypatch.setattr(downloader.config, "COOKIE_RETRY_DELAY", 0.0)
    monkeypatch.setattr(downloader.config, "COOKIES_FILE", str(tmp_path / "tidak_ada.txt"))
    calls = []

    class Y:
        def __init__(self, opts):
            self.opts = opts

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def extract_info(self, url, download=False):
            calls.append(self.opts)
            if self.opts.get("cookiesfrombrowser"):
                e = yt_dlp.utils.DownloadError("could not copy Chrome cookie database")
                e.__cause__ = PermissionError(13, "Permission denied")
                raise e
            return {"id": "ok"}

    monkeypatch.setattr(yt_dlp, "YoutubeDL", Y)
    info = downloader._extract({"cookiesfrombrowser": ("chrome",)}, "https://x")
    assert info["id"] == "ok"
    assert "cookiesfrombrowser" not in calls[-1]
    assert downloader._cookies_broken is True
    assert "Cookie browser" in capsys.readouterr().out   # user diberi tahu, bukan silent


# ---------- tangga format: platform dengan satu stream gabungan ----------

def test_download_turun_ke_best_kalau_format_tidak_ada(monkeypatch, tmp_path):
    monkeypatch.setattr(downloader, "_cookies_broken", True)  # hindari urusan cookie
    seen = []

    def fake_extract(opts, url, download=False):
        seen.append(opts["format"])
        if opts["format"] != "best":
            raise yt_dlp.utils.DownloadError("ERROR: Requested format is not available")
        out = tmp_path / "v.mp4"
        out.write_bytes(b"x" * 2048)
        return {"requested_downloads": [{"filepath": str(out)}]}

    monkeypatch.setattr(downloader, "_extract", fake_extract)
    got = downloader.download("https://www.tiktok.com/@a/video/1", tmp_path / "v")
    assert got.endswith("v.mp4")
    assert seen[-1] == "best"          # akhirnya pakai format paling permisif
    assert len(seen) > 1               # benar-benar menuruni tangga


def test_download_tidak_menelan_error_bukan_format(monkeypatch, tmp_path):
    monkeypatch.setattr(downloader, "_cookies_broken", True)

    def fake_extract(opts, url, download=False):
        raise yt_dlp.utils.DownloadError("ERROR: [youtube] x: This video is unavailable")

    monkeypatch.setattr(downloader, "_extract", fake_extract)
    with pytest.raises(yt_dlp.utils.DownloadError):
        downloader.download("https://www.youtube.com/watch?v=x", tmp_path / "v")


# ---------- peringatan runtime JS ----------

def test_peringatan_runtime_js_hilang(monkeypatch, capsys):
    import shutil
    monkeypatch.setattr(downloader, "_no_js_warned", False)
    monkeypatch.setattr(downloader.config, "JS_RUNTIMES", "deno")
    monkeypatch.setattr(shutil, "which", lambda name: None)
    downloader._warn_if_no_js_runtime()
    out = capsys.readouterr().out
    assert "runtime JS tidak ditemukan" in out
    assert "Made for Kids" in out


def test_peringatan_runtime_js_tidak_diulang(monkeypatch, capsys):
    import shutil
    monkeypatch.setattr(downloader, "_no_js_warned", False)
    monkeypatch.setattr(downloader.config, "JS_RUNTIMES", "deno")
    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/deno")
    downloader._warn_if_no_js_runtime()
    assert capsys.readouterr().out == ""


# ---------- profil browser eksplisit (cookie dari profil yang BENAR) ----------

@pytest.mark.parametrize("spec,expected", [
    ("chrome", ("chrome",)),
    ("chrome:Profile 7", ("chrome", "Profile 7")),
    ("Chrome:Profile 7", ("chrome", "Profile 7")),      # case-insensitive
    (" firefox:abc.default-release ", ("firefox", "abc.default-release")),
    ("edge", ("edge",)),
])
def test_profil_browser_diteruskan_ke_yt_dlp(monkeypatch, spec, expected):
    monkeypatch.setattr(downloader.config, "COOKIES_FROM_BROWSER", spec)
    monkeypatch.setattr(downloader, "_cookies_broken", False)
    monkeypatch.setattr(downloader.config, "COOKIES_FILE", "/tidak/ada.txt")
    assert downloader._cookie_opts()["cookiesfrombrowser"] == expected


def test_browser_tak_dikenal_diteruskan_apa_adanya(monkeypatch):
    monkeypatch.setattr(downloader.config, "COOKIES_FROM_BROWSER", "browseraneh:x")
    monkeypatch.setattr(downloader, "_cookies_broken", False)
    monkeypatch.setattr(downloader.config, "COOKIES_FILE", "/tidak/ada.txt")
    assert downloader._cookie_opts()["cookiesfrombrowser"] == ("browseraneh:x",)


def test_cookie_opts_kosong_kalau_cookies_broken(monkeypatch, tmp_path):
    monkeypatch.setattr(downloader.config, "COOKIES_FROM_BROWSER", "chrome:Profile 7")
    monkeypatch.setattr(downloader, "_cookies_broken", True)
    monkeypatch.setattr(downloader.config, "COOKIES_FILE", str(tmp_path / "tidak_ada.txt"))
    assert downloader._cookie_opts() == {}
