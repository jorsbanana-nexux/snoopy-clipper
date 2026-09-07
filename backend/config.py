"""
SEMUA setting Snoopy Clipper ada di file ini.
Bisa dioverride lewat file .env di root project (contoh: .env.example).
Agent masa depan: ubah perilaku app dari sini, jangan taburkan angka ajaib di file lain.
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DOWNLOADS_DIR = BASE_DIR / "downloads"   # cache video sumber + audio wav
LIBRARY_DIR = BASE_DIR / "library"      # klip jadi siap download + meta.json
JOBS_DIR = BASE_DIR / "jobs"           # progress job + file kerja sementara
MODELS_DIR = BASE_DIR / "models"        # model onnx face detector (auto-download)
FRONTEND_DIR = BASE_DIR / "frontend"

for d in (DOWNLOADS_DIR, LIBRARY_DIR, JOBS_DIR, MODELS_DIR):
    d.mkdir(parents=True, exist_ok=True)


def _load_env():
    """Loader .env super ringan (tanpa dependency tambahan).
    Paham komentar inline (`KEY=val  # catatan`) dan nilai berkutip."""
    env_file = BASE_DIR / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip()
        if val and val[0] in "\"'":
            end = val.find(val[0], 1)
            val = val[1:end] if end != -1 else val[1:]
        elif "#" in val:
            val = val.split("#", 1)[0].strip()
        os.environ.setdefault(key, val)

_load_env()


def env(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


# ============ COOKIES (jaga-jaga blokir YouTube "confirm you're not a bot") ============
# Cara 1 (termudah): isi nama browser yang dipakai login YouTube -> cookie dibaca langsung.
#   COOKIES_FROM_BROWSER=chrome   (pilihan: chrome / edge / firefox / brave / opera)
# Cara 2: ekspor cookies.txt (ekstensi "Get cookies.txt LOCALLY" saat buka youtube.com),
#   taruh file bernama cookies.txt di root project -> terdeteksi otomatis.
COOKIES_FROM_BROWSER = env("COOKIES_FROM_BROWSER", "")
COOKIES_FILE = env("COOKIES_FILE", "")

# ============ OTAK AI (Gemini) — satu-satunya layanan AI eksternal ============
GEMINI_API_KEY = env("GEMINI_API_KEY")
GEMINI_MODEL = env("GEMINI_MODEL", "gemini-3.6-flash")

# ============ OUTPUT ============
# "" = auto: 1080x1920 kalau sumber cukup besar, kalau tidak 720x1280.
# Isi "1080" atau "720" untuk memaksa.
FORCE_RESOLUTION = env("FORCE_RESOLUTION", "")
MAX_SOURCE_HEIGHT = int(env("MAX_SOURCE_HEIGHT", "1080"))  # turunkan ke 720 buat PC kentang

# ============ WHISPER (hemat CPU) ============
WHISPER_MODEL = env("WHISPER_MODEL", "small")      # tiny / base / small / medium
WHISPER_COMPUTE = env("WHISPER_COMPUTE", "int8")
WHISPER_BEAM = int(env("WHISPER_BEAM", "5"))  # 5 = akurasi lebih baik; 1 = tercepat

# ============ STRATEGI CEPAT (audio/video hanya seperlunya) ============
# 1 = pakai transkrip bawaan platform (instan) untuk otak + unduh video HANYA
#     rentang klip terpilih. 0 = jalur klasik (unduh penuh + whisper penuh).
CAPTIONS_FIRST = env("CAPTIONS_FIRST", "1") == "1"
# Video lebih panjang dari ini (detik): analisis visual frame DILEWATI di jalur cepat
# (otak tetap baca transkrip lengkap; hemat waktu & bandwidth besar).
BRAIN_FRAMES_MAX_DURATION = float(env("BRAIN_FRAMES_MAX_DURATION", "1200"))

# ============ PEMILIHAN MOMEN ============
MAX_CLIPS = int(env("MAX_CLIPS", "6"))
MIN_CLIP_SEC = float(env("MIN_CLIP_SEC", "15"))
MAX_CLIP_SEC = float(env("MAX_CLIP_SEC", "90"))

# ============ SPEED (low-spec friendly) ============
FACE_SAMPLE_INTERVAL = float(env("FACE_SAMPLE_INTERVAL", "1.0"))  # detik antar sampel wajah
LEAD_AHEAD_SEC = float(env("LEAD_AHEAD_SEC", "2.0"))  # kamera mulai menyorot 2 dtk SEBELUM ganti pembicara

# MOTION BLUR ala game kelas atas: aktif HANYA saat kamera pan (bukan selalu),
# blend halus dengan frame sebelumnya -> terasa sinematik, tetap tajam saat diam.
MOTION_BLUR = env("MOTION_BLUR", "1").lower() in ("1", "true", "on")
MOTION_BLUR_STRENGTH = float(env("MOTION_BLUR_STRENGTH", "0.35"))  # 0.1-0.5 (kecil = halus)

# SUBTITLE ala clipper profesional (opus.pro / snazo.app — wajar, bukan raksasa):
SUBTITLE_FONT = env("SUBTITLE_FONT", "Komika Axis")       # gaya komik; install font-nya dulu
SUBTITLE_CASE = env("SUBTITLE_CASE", "title")            # title = Huruf Besar Di Awal; upper; normal
SUBTITLE_SIZE_FRAC = float(env("SUBTITLE_SIZE_FRAC", "0.045"))  # ±4.5% tinggi frame = wajar
SUBTITLE_Y_FRAC = float(env("SUBTITLE_Y_FRAC", "0.70"))         # ideal 60-75%: area paling bersih dari UI platform

# SMART PLACEMENT (posisi subtitle pintar — tabrakan wajah, UI, teks bawaan, saliency)
PLACEMENT_SMART = env("PLACEMENT_SMART", "1").lower() in ("1", "true", "on")
UI_SAFE_RIGHT = float(env("UI_SAFE_RIGHT", "0.12"))     # sisi kanan: like/comment/share
UI_SAFE_BOTTOM = float(env("UI_SAFE_BOTTOM", "0.15"))   # sisi bawah: username/deskripsi
SUBTITLE_MIN_Y_FRAC = float(env("SUBTITLE_MIN_Y_FRAC", "0.18"))  # jangan lebih atas dari ini
SUBTITLE_POP = float(env("SUBTITLE_POP", "1.18"))               # overshoot bounce per kata
SUBTITLE_POP_MS = int(env("SUBTITLE_POP_MS", "80"))             # durasi pop (ms)
HIGHLIGHT_COLOR = env("HIGHLIGHT_COLOR", "00C8FF")              # BGR ASS: emas MrBeast

# GRADE "GAME ULTRA": ketajaman tekstur + bayangan pekat + warna hidup + kulit hangat.
# Semua filter MURAH (per-pixel, satu pass, biaya CPU kecil) — tetap low-spec friendly.
GAME_ULTRA = env("GAME_ULTRA", "1").lower() in ("1", "true", "on")
UNSHARP_AMOUNT = float(env("UNSHARP_AMOUNT", "0.45"))    # texture ultra; 0 = off (0.3-0.6 subtle)
EQ_CONTRAST = float(env("EQ_CONTRAST", "1.06"))          # kontras naik sedikit
EQ_GAMMA = float(env("EQ_GAMMA", "0.94"))                # gamma turun sedikit -> shadow pekat
EQ_SATURATION = float(env("EQ_SATURATION", "1.12"))     # warna lebih hidup
WARM_HUE_DEG = float(env("WARM_HUE_DEG", "2.0"))        # rotasi hue hangat (derajat) -> rona
# kemerahan kulit ala subsurface scattering; filter hue = paling murah (ovh ~5%)

# OTAK MULTIMODAL: kirim cuplikan frame ke Gemini supaya bisa "melihat" video
BRAIN_MULTIMODAL = env("BRAIN_MULTIMODAL", "1").lower() in ("1", "true", "on")
BRAIN_FRAME_INTERVAL = float(env("BRAIN_FRAME_INTERVAL", "8"))  # 1 frame tiap N detik
BRAIN_MAX_FRAMES = int(env("BRAIN_MAX_FRAMES", "48"))
X264_PRESET = env("X264_PRESET", "veryfast")  # mau kualitas++: "medium" (lebih lambat)
X264_CRF = env("X264_CRF", "20")
