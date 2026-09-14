"""Kontrak: challenge JS YouTube (EJS) harus selalu punya runtime + skrip.

Bukti lapangan (yt-dlp issue #16693 & #16333, direproduksi 2026-09-14):
video "Made for Kids" gagal dengan pesan PERSIS

    ERROR: [youtube] <id>: This video is not available

saat tidak ada runtime JS / skrip EJS. Pesan itu TIDAK menyebut cookie,
sehingga fallback cookie di downloader._extract juga tidak pernah jalan —
job mati dengan pesan yang menyesatkan.
"""
import yt_dlp

from backend import downloader


def test_js_opts_default_mengaktifkan_deno_dan_skrip_ejs():
    opts = downloader._js_opts()
    assert opts["js_runtimes"] == {"deno": {"path": None}}
    assert opts["remote_components"] == {"ejs:github"}


def test_js_opts_hormati_path_dan_daftar_runtime(monkeypatch):
    monkeypatch.setattr(downloader.config, "JS_RUNTIMES", "deno,node")
    monkeypatch.setattr(downloader.config, "JS_RUNTIME_PATH", "C:/nodejs/node.exe")
    opts = downloader._js_opts()
    assert set(opts["js_runtimes"]) == {"deno", "node"}
    assert opts["js_runtimes"]["node"] == {"path": "C:/nodejs/node.exe"}


def test_js_opts_kosong_artinya_mati(monkeypatch):
    monkeypatch.setattr(downloader.config, "JS_RUNTIMES", "")
    monkeypatch.setattr(downloader.config, "REMOTE_COMPONENTS", "")
    assert downloader._js_opts() == {}


def test_js_opts_buang_nama_runtime_tak_dikenal(monkeypatch):
    monkeypatch.setattr(downloader.config, "JS_RUNTIMES", "deno,halo")
    assert set(downloader._js_opts()["js_runtimes"]) == {"deno"}


def test_kegagalan_cookie_di_rantai_exception_terdeteksi():
    """Chrome yang terkunci membuat CookieLoadError, tapi DownloadError yang
    sampai ke atas bisa berbunyi 'This video is not available' tanpa kata
    'cookie' sama sekali. Deteksi harus menelusuri __cause__/__context__."""
    CookieLoadError = type("CookieLoadError", (Exception,), {})
    outer = yt_dlp.utils.DownloadError(
        "ERROR: [youtube] abc: This video is not available")
    outer.__cause__ = CookieLoadError("Failed to load cookies")
    assert downloader._is_cookie_failure(outer) is True


def test_error_biasa_tetap_dianggap_bukan_cookie():
    e = yt_dlp.utils.DownloadError("ERROR: [youtube] abc: This video is unavailable")
    assert downloader._is_cookie_failure(e) is False


def test_fallback_cookie_jalan_walau_pesannya_bukan_soal_cookie(monkeypatch):
    """Regresi: dulu fallback cuma jalan kalau 'cookie' ada di pesan akhir."""
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
            calls.append(self.opts)
            if self.opts.get("cookiesfrombrowser"):
                e = yt_dlp.utils.DownloadError(
                    "ERROR: [youtube] abc: This video is not available")
                e.__cause__ = type("CookieLoadError", (Exception,), {})("boom")
                raise e
            return {"id": "ok", "title": "T", "duration": 10.0}

    monkeypatch.setattr(yt_dlp, "YoutubeDL", FakeYDL)
    info = downloader._extract({"cookiesfrombrowser": ("chrome",)}, "https://x")
    assert info["id"] == "ok"
    assert len(calls) == 2
    assert "cookiesfrombrowser" not in calls[1]
