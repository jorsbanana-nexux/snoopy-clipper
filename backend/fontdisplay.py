"""Milky Moringa Bold (fikryalstudio) — font display pilihan owner
2026-09-12 untuk HOOK & THUMBNAIL, diunduh dari 1001fonts.

Fakta yang diketahui owner saat memutuskan:
- lisensi versi ini "personal use" (README di dalam zip); owner memutuskan
  "tetap terapkan" dan menanggung sendiri — 2026-09-12
- charset LENGKAP (240 glyph): angka 0-9 + tanda baca ada semua — diuji
  sebelum dipasang (beda dari Milky Way DEMO yang bolong)

Perilaku: unduh SEKALI -> models/fonts/milky-moringa-bold.ttf (cache
permanen, pola sama seperti anton.ttf). Gagal unduh -> None -> pemanggil
memakai fallback (Anton / font sistem). TIDAK PERNAH raise."""
import io
import urllib.request
import zipfile

from . import config

_URL = "https://www.1001fonts.com/download/milky-moringa.zip"
_NAME = "milky-moringa-bold.ttf"
_INNER = "Milky Moringa Bold.ttf"


def ensure():
    """Pastikan font ada di cache; kembalikan Path, atau None bila gagal."""
    p = config.MODELS_DIR / "fonts" / _NAME
    try:
        if p.exists():
            return p
        p.parent.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(_URL, headers={"User-Agent": "Mozilla/5.0"})
        data = urllib.request.urlopen(req, timeout=30).read()
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            p.write_bytes(z.read(_INNER))
        return p
    except Exception:
        return None
