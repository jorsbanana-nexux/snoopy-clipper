"""
cek_lingkungan.py — jalankan SEBELUM melaporkan "video tidak bisa diproses".

Jalankan di root project (folder yang sama dengan backend/):

    python cek_lingkungan.py
    python cek_lingkungan.py "https://www.youtube.com/watch?v=XXXXXXXXXXX"

Script ini memeriksa 5 hal yang paling sering bikin job Snoopy Clipper mati di
tahap "info", lalu mencoba ekstraksi nyata supaya Anda tahu apakah masalahnya
di mesin Anda atau di videonya.
"""
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OK, BAD, WARN = "[ OK ]", "[GAGAL]", "[WARN]"
problems = []


def _run(cmd, timeout=90):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return (r.returncode, (r.stdout or "") + (r.stderr or ""))
    except Exception as e:  # noqa: BLE001
        return 1, str(e)


print("=" * 68)
print("  SNOOPY CLIPPER — CEK LINGKUNGAN (YouTube / video anak)")
print("=" * 68)

# 1. ffmpeg
print("\n1) ffmpeg / ffprobe")
for exe in ("ffmpeg", "ffprobe"):
    p = shutil.which(exe)
    if p:
        print(f"   {OK} {exe}: {p}")
    else:
        print(f"   {BAD} {exe} tidak ada di PATH — unduh/merge/ukur video akan gagal.")
        problems.append(f"{exe} tidak ada di PATH")

# 2. yt-dlp + versi
print("\n2) yt-dlp")
try:
    import yt_dlp
    ver = yt_dlp.version.__version__
    print(f"   {OK} yt-dlp {ver} terpasang")
except Exception as e:  # noqa: BLE001
    print(f"   {BAD} yt-dlp tidak bisa di-import: {e}")
    problems.append("yt-dlp tidak terpasang")
    yt_dlp = None

# 3. skrip pemecah challenge (yt-dlp-ejs)
print("\n3) skrip pemecah challenge JS (yt-dlp-ejs)")
ejs_ok = False
try:
    import yt_dlp_ejs  # noqa: F401
    ejs_ok = True
    print(f"   {OK} paket yt-dlp-ejs terpasang")
except Exception:  # noqa: BLE001
    print(f"   {WARN} paket yt-dlp-ejs TIDAK terpasang.")
    print("        Perbaiki:  pip install -U \"yt-dlp[default]\"")
    print("        Atau andalkan unduhan otomatis: set REMOTE_COMPONENTS=ejs:github di .env")

# 4. runtime JavaScript
print("\n4) runtime JavaScript (deno disarankan)")
runtime = None
for name in ("deno", "node", "qjs"):
    p = shutil.which(name)
    if p:
        _, out = _run([p, "--version"], timeout=20)
        print(f"   {OK} {name}: {out.strip().splitlines()[0] if out.strip() else p}")
        runtime = runtime or name
if runtime is None:
    print(f"   {BAD} tidak ada runtime JS yang ketemu di PATH.")
    print("        Windows:  winget install DenoLand.Deno   (lalu buka terminal baru)")
    problems.append("tidak ada runtime JS (deno/node) di PATH")

# 5. cookie
print("\n5) cookie")
cf = ROOT / "cookies.txt"
if cf.exists():
    size = cf.stat().st_size
    print(f"   {OK} {cf.name} ada ({size} byte)")
    if size < 200:
        print(f"   {WARN} isinya mencurigakan kecil — ekspor ulang saat login youtube.com")
else:
    print(f"   {WARN} cookies.txt tidak ada di root project (boleh, kalau video publik).")
# 5b. UJI NYATA pembacaan cookie dari browser (ini yang bikin owner bingung:
# berhasil di .env, tapi tetap gagal karena file-nya terkunci Chrome).
try:
    from backend import config  # noqa: PLC0415
    browser = config.COOKIES_FROM_BROWSER
    if browser:
        print(f"   COOKIES_FROM_BROWSER={browser} -> mencoba membaca sungguhan…")
        try:
            import yt_dlp.cookies as ytc  # noqa: PLC0415
            browser_name, _, profile = browser.partition(":")
            profile = profile.strip() or None
            if profile:
                print(f"        (profil eksplisit: {profile})")
            jar = ytc.extract_cookies_from_browser(browser_name.strip(), profile)
            n_all = len(jar)
            n_yt = sum(1 for c in jar if "youtube" in (c.domain or ""))
            if n_yt:
                print(f"   {OK} cookie terbaca: {n_all} total, {n_yt} untuk youtube.com")
            else:
                print(f"   {WARN} cookie terbaca ({n_all}) TAPI tidak ada cookie youtube.com")
                print("        -> Anda belum login YouTube di browser itu, atau profil salah.")
        except Exception as e:  # noqa: BLE001
            msg = str(e)
            print(f"   {BAD} gagal membaca cookie dari {browser}: {msg[:140]}")
            if "permission denied" in msg.lower() or "errno 13" in msg.lower():
                print("        Penyebab: file Cookies.sqlite DIKUNCI. Tutup SEMUA jendela")
                print("        Chrome (cek juga tray/background) lalu jalankan ulang.")
                print("        Paling stabil: ekspor cookies.txt dan kosongkan COOKIES_FROM_BROWSER.")
            elif "could not copy" in msg.lower():
                print("        Penyebab: App-Bound Encryption (Chrome 127+). yt-dlp tidak")
                print("        bisa mendekripsi cookie Chrome profil ini.")
                print("        Solusi: pakai cookies.txt, atau COOKIES_FROM_BROWSER=firefox.")
            problems.append(f"cookie browser ({browser}) tidak terbaca")
    else:
        print("   COOKIES_FROM_BROWSER kosong (mode cookies.txt / tanpa cookie).")
except Exception:  # noqa: BLE001
    pass

# 6. uji ekstraksi nyata
url = sys.argv[1] if len(sys.argv) > 1 else "https://www.youtube.com/watch?v=Hh-tOGUeX9k"
print(f"\n6) Uji ekstraksi nyata\n   URL: {url}")
if yt_dlp is None:
    print("   dilewati (yt-dlp tidak ada)")
else:
    opts = {"quiet": True, "no_warnings": True, "skip_download": True, "noplaylist": True}
    try:
        from backend import config  # noqa: PLC0415
        names = [n.strip() for n in (config.JS_RUNTIMES or "").split(",") if n.strip()]
        if names:
            opts["js_runtimes"] = {n: {"path": config.JS_RUNTIME_PATH or None} for n in names}
        comps = [c.strip() for c in (config.REMOTE_COMPONENTS or "").split(",") if c.strip()]
        if comps:
            opts["remote_components"] = set(comps)
        print(f"   opsi: js_runtimes={opts.get('js_runtimes')} remote_components={opts.get('remote_components')}")
    except Exception:  # noqa: BLE001
        pass
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
        print(f"   {OK} BERHASIL: {info.get('title')!r} ({info.get('duration')} detik)")
    except Exception as e:  # noqa: BLE001
        msg = str(e)
        print(f"   {BAD} GAGAL: {msg[:200]}")
        low = msg.lower()
        if "is not available" in low:
            print("\n   >>> Pesan ini = challenge JS YouTube belum dipecahkan.")
            print("       Itu penyebab khas video 'Made for Kids' / YouTube Kids.")
            print("       Butuh DUA hal sekaligus:")
            print("         a) runtime JS (deno) ada di PATH")
            print("         b) skrip yt-dlp-ejs -> pip install -U \"yt-dlp[default]\"")
            print("            ATAU REMOTE_COMPONENTS=ejs:github di .env")
            problems.append("challenge JS belum bisa dipecahkan")
        elif "is unavailable" in low or "private" in low:
            print("\n   >>> Video-nya sendiri tidak tersedia (dihapus/privat/geo-blok).")
            print("       Coba buka URL-nya di browser dengan akun yang sama.")
        elif "cookie" in low or "sign in" in low or "bot" in low:
            print("\n   >>> Butuh cookie login — pakai cookies.txt di root project.")
            problems.append("butuh cookie login")
        else:
            problems.append("ekstraksi gagal")

print("\n" + "=" * 68)
if problems:
    print("RINGKASAN MASALAH:")
    for i, p in enumerate(problems, 1):
        print(f"  {i}. {p}")
    print("\nPerbaiki yang di atas, lalu jalankan script ini lagi.")
    sys.exit(1)
print("Semua cek lolos — lingkungan siap.")
