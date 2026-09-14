"""Kontrak: kesalahan encoding di .env TIDAK BOLEH mematikan aplikasi.

Kejadian nyata 2026-09-14: `.env` berisi emoji `⚠️` (byte `e2 9a a0 ef b8 8f`).
`Path.read_text()` memakai encoding lokal — di Windows cp1252 — dan byte `0x8f`
tidak ada di cp1252, sehingga muncul `UnicodeDecodeError` DI DALAM IMPORT
`backend.config`. Akibatnya uvicorn mati sebelum jalan dan browser menampilkan
"localhost refused to connect": bukan 1 job yang gagal, tapi seluruh aplikasi.
"""
import os

from backend import config


def _load(monkeypatch, tmp_path, data: bytes) -> None:
    (tmp_path / ".env").write_bytes(data)
    monkeypatch.setattr(config, "BASE_DIR", tmp_path)
    for key in ("FOO", "BAR", "KUNCI"):
        os.environ.pop(key, None)
    config._load_env()


def test_env_dengan_emoji_peringatan_tidak_lagi_crash(monkeypatch, tmp_path):
    """Ini byte persis yang menjatuhkan aplikasi owner."""
    data = (
        "# !! SELALU SEBUT PROFIL kalau Chrome > 1 profil\n"
        "COOKIES_FROM_BROWSER=chrome:Profile 7\n"
        "# \u26a0\ufe0f peringatan yang bikin crash\n"
        "FOO=bar\n"
    ).encode("utf-8")
    assert b"\x8f" in data            # pastikan memang ada byte 0x8f
    _load(monkeypatch, tmp_path, data)
    assert os.environ["FOO"] == "bar"
    assert os.environ["COOKIES_FROM_BROWSER"] == "chrome:Profile 7"


def test_env_utf8_dengan_em_dash_dan_emoji(monkeypatch, tmp_path):
    data = "BAR=aman \u2014 \U0001f525 \u2705\n".encode("utf-8")
    _load(monkeypatch, tmp_path, data)
    assert os.environ["BAR"].startswith("aman")


def test_env_dengan_bom_notepad(monkeypatch, tmp_path):
    """Notepad bisa menyimpan UTF-8 + BOM; kunci pertama tidak boleh kotor."""
    data = b"\xef\xbb\xbf" + b"FOO=tanpa-bom\n"
    _load(monkeypatch, tmp_path, data)
    assert os.environ["FOO"] == "tanpa-bom"
    assert "\ufefffoo" not in {k.lower() for k in os.environ}


def test_env_cp1252_lama_tetap_terbaca(monkeypatch, tmp_path):
    """Berkas lama yang disimpan sebagai cp1252 (0x92 = kutip tunggal pintar)."""
    data = b"FOO=it\x92s fine\n"
    _load(monkeypatch, tmp_path, data)
    assert "fine" in os.environ["FOO"]


def test_env_ascii_biasa(monkeypatch, tmp_path):
    _load(monkeypatch, tmp_path, b"FOO=1\nBAR=2\n")
    assert (os.environ["FOO"], os.environ["BAR"]) == ("1", "2")


def test_env_tak_terbaca_tidak_mematikan_app(monkeypatch, tmp_path):
    """Kalau berkas benar-benar tak bisa dibaca, pakai default — jangan crash."""
    (tmp_path / ".env").write_bytes(b"FOO=x\n")
    monkeypatch.setattr(config, "BASE_DIR", tmp_path)

    def boom(_path):
        raise OSError("disk error")

    monkeypatch.setattr(config, "_read_env_text", boom)
    config._load_env()  # tidak boleh melempar


def test_komentar_dan_kutip_masih_dipaham(monkeypatch, tmp_path):
    data = (
        'FOO="nilai berkutip"  # komentar inline\n'
        "BAR=nilai # komentar inline\n"
        "# baris komentar penuh\n"
        "\n"
    ).encode("utf-8")
    _load(monkeypatch, tmp_path, data)
    assert os.environ["FOO"] == "nilai berkutip"
    assert os.environ["BAR"] == "nilai"


def test_env_example_murni_ascii():
    """Agar menyalin .env.example ke .env tidak pernah menyuntik non-ASCII."""
    raw = (config.BASE_DIR / ".env.example").read_bytes()
    bad = [(i, b) for i, b in enumerate(raw) if b > 127]
    assert not bad, f"ada {len(bad)} byte non-ASCII, pertama di offset {bad[0][0]}"
