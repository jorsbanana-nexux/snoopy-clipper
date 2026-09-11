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
LOGS_DIR = BASE_DIR / "logs"            # log job JSONL (observability ringan)

for d in (DOWNLOADS_DIR, LIBRARY_DIR, JOBS_DIR, MODELS_DIR, LOGS_DIR):
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

# SNOOPY_TEST_DEFAULTS=1 (dipasang otomatis oleh tests/conftest.py):
# suite HARUS hijau di PC mana pun -> test selalu menguji DEFAULT, bukan
# override di .env lokal siapa pun. Mode produksi TIDAK terpengaruh.
if not os.environ.get("SNOOPY_TEST_DEFAULTS"):
    _load_env()


def env(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


# ============ AUTO-POST: YouTube Shorts (Google OAuth) ============
# Daftar: console.cloud.google.com -> project baru -> aktifkan YouTube Data API v3
# -> OAuth consent screen (External, test user = akunmu) -> OAuth client ID
# (Web application, redirect: http://localhost:8000/api/publish/callback).
# Client ID/Secret cukup ditempel di .env — JANGAN pernah dikirim via chat.
YT_CLIENT_ID = env("YT_CLIENT_ID")
YT_CLIENT_SECRET = env("YT_CLIENT_SECRET")
YT_REDIRECT_URI = env("YT_REDIRECT_URI", "http://localhost:8000/api/publish/callback")
# Token OAuth disimpan di file (refresh token long-lived) — masuk volume Docker.
YT_TOKEN_FILE = env("YT_TOKEN_FILE", "")  # kosong = default JOBS_DIR/yt_token.json
PUBLISH_PRIVACY = env("PUBLISH_PRIVACY", "public")  # public / unlisted / private

# ============ SIAP-PRODUK: auth ringan + kuota harian ============
# API_KEY kosong = mode lokal LAMA (tanpa login, semua request diizinkan).
# Diisi = wajib kirim header `X-API-Key` (atau ?key=) utk endpoint /api/clip,
# /api/jobs, /api/library — tanpa ini, deploy publik = orang asing memakai
# Gemini key & CPU kita gratis. Frontend otomatis minta kunci & menyimpannya.
API_KEY = env("API_KEY")
# Batas menit video-per-hari (server UTC). 0 = tanpa batas (mode lokal).
# Fondasi billing: diisi saat dipakai orang lain / hosting publik.
DAILY_MINUTES_LIMIT = float(env("DAILY_MINUTES_LIMIT", "0"))

# ============ COOKIES (jaga-jaga blokir YouTube "confirm you're not a bot") ============
# Cara 1 (isi nama browser -> cookie dibaca langsung dari profilnya):
#   COOKIES_FROM_BROWSER=chrome   (pilihan: chrome / edge / firefox / brave / opera)
#   RAWAN GAGAL di Windows -- BUKAN cuma saat browser terbuka: Chrome versi
#   baru (App-Bound Encryption, ~2024+) mengenkripsi Cookies.sqlite dengan
#   kunci terikat OS sehingga yt-dlp sering tetap gagal MENYALIN file itu
#   ("Could not copy Chrome cookie database", yt-dlp issue #7271) walau
#   Chrome sudah ditutup. Kalau ini terjadi, server otomatis jatuh ke Cara 2
#   (cookies.txt, kalau file itu ada) sebelum akhirnya coba tanpa cookie sama
#   sekali -- video publik tetap berhasil; video yang butuh login/umur 18+
#   TETAP bisa lolos asal Cara 2 terisi.
# Cara 2 (LEBIH STABIL, disarankan kalau Cara 1 sering gagal seperti di atas):
#   ekspor cookies.txt (ekstensi "Get cookies.txt LOCALLY" saat login di
#   youtube.com), taruh file bernama cookies.txt di root project -> terdeteksi
#   otomatis. Boleh isi KEDUANYA sekaligus (fallback otomatis Cara 1 -> Cara 2
#   -> tanpa cookie) atau cukup Cara 2 saja (lebih cepat, tak buang waktu coba
#   Cara 1 yang sudah diketahui gagal tiap kali).
COOKIES_FROM_BROWSER = env("COOKIES_FROM_BROWSER", "")
COOKIES_FILE = env("COOKIES_FILE", "")

# ============ MULTI-USER & BILLING (gap #6 — default NONAKTIF) ============
# MULTIUSER=1 -> registrasi/login akun + kunci API per-user + kuota per plan
# + halaman login otomatis di UI + endpoint billing (/api/auth/*, /api/billing/*).
# Saat MULTIUSER=1 biarkan API_KEY KOSONG (auth per-user yang berlaku).
MULTIUSER = env("MULTIUSER", "0") == "1"
PLAN_FREE_DAILY_MINUTES = float(env("PLAN_FREE_DAILY_MINUTES", "30"))
PLAN_PRO_DAILY_MINUTES = float(env("PLAN_PRO_DAILY_MINUTES", "240"))
PLAN_PRO_PRICE_IDR = int(env("PLAN_PRO_PRICE_IDR", "39000"))
# Email akun admin — bisa grant plan manual via POST /api/billing/grant.
ADMIN_EMAIL = env("ADMIN_EMAIL", "")
# Midtrans opsional: TANPA ini checkout otomatis mode MANUAL (transfer bank,
# admin grant) — bisa jualan tanpa menunggu approve payment gateway.
# Server key sandbox berawalan "SB-Mid-server-". Webhook: /api/billing/midtrans-webhook
MIDTRANS_SERVER_KEY = env("MIDTRANS_SERVER_KEY", "")
MIDTRANS_IS_PRODUCTION = env("MIDTRANS_IS_PRODUCTION", "0") == "1"
# Login dengan Google (opsional, gap #6): default MEMAKAI client OAuth
# YouTube (YT_CLIENT_ID/SECRET) — cukup tambah redirect URI
# http://localhost:8000/api/auth/google/callback di Google Cloud Console.
# Scope login: openid+email+profile saja (BUKAN YouTube).
GOOGLE_LOGIN_CLIENT_ID = env("GOOGLE_LOGIN_CLIENT_ID", "")
GOOGLE_LOGIN_CLIENT_SECRET = env("GOOGLE_LOGIN_CLIENT_SECRET", "")

# ============ OTAK AI (Gemini) — satu-satunya layanan AI eksternal ============
GEMINI_API_KEY = env("GEMINI_API_KEY")
GEMINI_MODEL = env("GEMINI_MODEL", "gemini-3.1-pro-preview")  # tertinggi duluan, turun otomatis kalau bermasalah

# RANTAI FALLBACK MODEL: kalau model utama gagal (503 high demand, rate limit,
# error server, dll), otomatis coba lagi model utama sampai GEMINI_PRIMARY_RETRIES
# kali, lalu turun ke daftar model cadangan (GEMINI_FALLBACK_MODELS) satu per satu
# (dalam urutan yang ditulis) sampai ada yang berhasil. Diam-diam log ke console
# tiap kali pindah model, supaya kelihatan di log kapan fallback terjadi.
GEMINI_PRIMARY_RETRIES = int(env("GEMINI_PRIMARY_RETRIES", "3"))  # percobaan model utama sebelum turun (perisai badai 503)
# CATATAN: gemini-2.5-pro DIBUANG dari daftar — Google sudah mematikannya
# (404 permanen "no longer available for new users"), jadi kalau tetap ada
# di sini, SETIAP job membuang satu percobaan penuh ke model yang pasti mati.
GEMINI_FALLBACK_MODELS = env(
    "GEMINI_FALLBACK_MODELS",
    "gemini-3.8-flash,gemini-3.7-flash,gemini-3.6-flash,gemini-2.5-flash",
)  # urutan TURUN dari yang paling tinggi: flash terbaru -> lama
GEMINI_RETRY_DELAY_SEC = float(env("GEMINI_RETRY_DELAY_SEC", "2.0"))  # jeda antar percobaan

# ============ OUTPUT ============
# "" = auto: 1080x1920 kalau sumber cukup besar, kalau tidak 720x1280.
# Isi "1080" atau "720" untuk memaksa.
FORCE_RESOLUTION = env("FORCE_RESOLUTION", "")
MAX_SOURCE_HEIGHT = int(env("MAX_SOURCE_HEIGHT", "1080"))  # turunkan ke 720 buat PC kentang

# ============ WHISPER (hemat CPU) ============
WHISPER_MODEL = env("WHISPER_MODEL", "small")      # tiny / base / small / medium
WHISPER_COMPUTE = env("WHISPER_COMPUTE", "int8")
WHISPER_BEAM = int(env("WHISPER_BEAM", "1"))  # 1 = tercepat (ketepatan waktu kata tetap); 5 = anti-typo maksimal

# ============ DIARIZATION (opsional, default MATI) ============
# Label "siapa bicara" per baris/kata -> otak Gemini bisa pilih momen per pembicara.
# Butuh: pip install -r requirements-diarize.txt + token HuggingFace (lihat backend/diarize.py).
# Gagal apa pun (library/token tidak ada) -> pipeline jalan normal TANPA label, tidak pernah error.
DIARIZE = env("DIARIZE", "0") == "1"
DIARIZE_TOKEN = env("DIARIZE_TOKEN", "")
DIARIZE_MODEL = env("DIARIZE_MODEL", "pyannote/speaker-diarization-3.1")

# ============ THUMBNAIL (WAJIB ada, default NYALA) ============
# Selalu ada file .jpg per klip (rantai fallback berlapis, tidak pernah gagal).
# 0 hanya kalau benar-benar mau matikan.
THUMBNAIL = env("THUMBNAIL", "1") == "1"

# TEKS JUDUL KHUSUS PODCAST (jenis konten lain TIDAK berubah, tetap polos):
# judul klip dari library -> putih bersih TANPA outline, hanya shadow hitam
# blur lebar halus; emoji tersenyum kartun selalu menumpang di atas teks;
# + 1 emoji topik (topic_tag dari otak Gemini) di posisi strategis otomatis.
# 0 = semua thumbnail polos seperti versi sebelumnya.
THUMB_TEXT = env("THUMB_TEXT", "1") == "1"
# Font teks podcast: kosong = auto (file ttf/otf pertama di assets/fonts/ —
# letakkan Liberica.ttf milikmu di situ — lalu fallback font sistem bold).
# Isi path utk memaksa font tertentu (mis. /path/Liberica.ttf).
THUMB_FONT_FILE = env("THUMB_FONT_FILE", "")

# ============ STRATEGI CEPAT (audio/video hanya seperlunya) ============
# 1 = pakai transkrip bawaan platform (instan) untuk otak + unduh video HANYA
#     rentang klip terpilih. 0 = jalur klasik (unduh penuh + whisper penuh).
CAPTIONS_FIRST = env("CAPTIONS_FIRST", "1") == "1"
# Video lebih panjang dari ini (detik): analisis visual frame DILEWATI di jalur cepat.
#
# Penting: caption-first hanya terasa cepat bila kita TIDAK mengunduh lalu
# mendekode seluruh video sebelum memilih momen. Empat menit masih cukup untuk
# memberi konteks visual video pendek; di atas itu, transkrip dipakai dulu dan
# video diambil hanya untuk rentang momen yang benar-benar dipilih.
BRAIN_FRAMES_MAX_DURATION = float(env("BRAIN_FRAMES_MAX_DURATION", "240"))
BRAIN_FRAMES_PROXY = env("BRAIN_FRAMES_PROXY", "1") == "1"  # video panjang: proxy visual murah (worst, tanpa audio) utk otak

# ============ PEMILIHAN MOMEN ============
MAX_CLIPS = int(env("MAX_CLIPS", "100"))  # PLAFON pengaman saja — jumlah klip = keputusan otak AI sesuai kualitas video
MIN_CLIP_SEC = float(env("MIN_CLIP_SEC", "15"))
MAX_CLIP_SEC = float(env("MAX_CLIP_SEC", "90"))

# ============ SPEED (low-spec friendly) ============
FACE_SAMPLE_INTERVAL = float(env("FACE_SAMPLE_INTERVAL", "0.5"))  # detik antar sampel wajah (0.5 = reaksi kamera 2x lebih gesit, tetap ringan)
LEAD_AHEAD_SEC = float(env("LEAD_AHEAD_SEC", "2.0"))  # kamera mulai menyorot 2 dtk SEBELUM ganti pembicara

# MOTION BLUR ala game kelas atas: aktif HANYA saat kamera pan (bukan selalu),
# blend halus dengan frame sebelumnya -> terasa sinematik, tetap tajam saat diam.
MOTION_BLUR = env("MOTION_BLUR", "1").lower() in ("1", "true", "on")
MOTION_BLUR_STRENGTH = float(env("MOTION_BLUR_STRENGTH", "0.35"))  # 0.1-0.5 (kecil = halus)

# SUBTITLE ala clipper profesional (opus.pro / snazo.app — wajar, bukan raksasa):
SUBTITLE_FONT = env("SUBTITLE_FONT", "Komika Axis")       # gaya komik; install font-nya dulu
SUBTITLE_CASE = env("SUBTITLE_CASE", "title")            # title = Huruf Besar Di Awal; upper; normal
SUBTITLE_SIZE_FRAC = float(env("SUBTITLE_SIZE_FRAC", "0.0494"))  # ±4.94% tinggi frame (+3% dari 0.048: lebih terbaca di HP)
SUBTITLE_SPLIT_LAYER = env("SUBTITLE_SPLIT_LAYER", "1") == "1"  # SPLIT LAYER duo (bisa dimatikan total utk rollback instan)
SUBTITLE_FADE_MS = int(env("SUBTITLE_FADE_MS", "220"))  # fade-out halus + blur mini saat frasa menutup (0 = potong keras)
SUBTITLE_Y_FRAC = float(env("SUBTITLE_Y_FRAC", "0.70"))         # ideal 60-75%: area paling bersih dari UI platform

# SMART PLACEMENT (posisi subtitle pintar — tabrakan wajah, UI, teks bawaan, saliency)
PLACEMENT_SMART = env("PLACEMENT_SMART", "1").lower() in ("1", "true", "on")
UI_SAFE_RIGHT = float(env("UI_SAFE_RIGHT", "0.12"))     # sisi kanan: like/comment/share
UI_SAFE_BOTTOM = float(env("UI_SAFE_BOTTOM", "0.15"))   # sisi bawah: username/deskripsi
SUBTITLE_MIN_Y_FRAC = float(env("SUBTITLE_MIN_Y_FRAC", "0.18"))  # jangan lebih atas dari ini
SUBTITLE_POP = float(env("SUBTITLE_POP", "1.18"))               # overshoot bounce per kata
SUBTITLE_POP_MS = int(env("SUBTITLE_POP_MS", "80"))             # durasi pop (ms)
HIGHLIGHT_COLOR = env("HIGHLIGHT_COLOR", "FFAA00")              # BGR ASS: BIRU STABILO (#00AAFF RGB) ala MrBeast
KARAOKE_FADE_MS = int(env("KARAOKE_FADE_MS", "70"))             # kecepatan transisi warna karaoke (ms)

# GRADE "GAME ULTRA": ketajaman tekstur + bayangan pekat + warna hidup + kulit hangat.
# Semua filter MURAH (per-pixel, satu pass, biaya CPU kecil) — tetap low-spec friendly.
GAME_ULTRA = env("GAME_ULTRA", "0").lower() in ("1", "true", "on")
UNSHARP_AMOUNT = float(env("UNSHARP_AMOUNT", "0.45"))    # texture ultra; 0 = off (0.3-0.6 subtle)
EQ_CONTRAST = float(env("EQ_CONTRAST", "1.06"))          # kontras naik sedikit
EQ_GAMMA = float(env("EQ_GAMMA", "0.94"))                # gamma turun sedikit -> shadow pekat
EQ_SATURATION = float(env("EQ_SATURATION", "1.12"))     # warna lebih hidup
WARM_HUE_DEG = float(env("WARM_HUE_DEG", "2.0"))

# ============ BGM VIRAL (incompetech / Kevin MacLeod, CC BY 4.0) ============
# Mood dipilih OTAK di panggilan Gemini yang sama (nol biaya/waktu tambahan).
# Track diunduh SEKALI per track lalu cache permanen (mono 64k, ~0.5-1.5MB).
# BGM wajib selalu ada; intensitas kecil & nyaman. Kredit otomatis -> meta.json.
BGM = env("BGM", "1").lower() in ("1", "true", "on")
BGM_VOLUME = float(env("BGM_VOLUME", "0.15"))  # 15% dari suara utama

# ============ DAGING KLIP v1: voice, dead-air, hook, watermark ============
# VOICE TREATMENT: highpass + denoise + kompresi + loudness -14 LUFS
# (standar platform) — klip terdengar 'studio'. 0 = perilaku lama.
VOICE_TREAT = env("VOICE_TREAT", "1") == "1"
# DEAD-AIR: jeda napas panjang di tengah klip dipotong (jump cut) memakai
# timestamp kata Whisper. Hanya gap interior >= DEADAIR_GAP dtk, tiap sisi
# wajib >= 1.2 dtk, total buangan <= 40%. 0 = rollback instan.
DEADAIR = env("DEADAIR", "1") == "1"
DEADAIR_GAP = float(env("DEADAIR_GAP", "0.6"))
# WATERMARK 'SNOOPY CLIPPER' (kuning+putih tebal, semi-transparan, kiri-atas).
WATERMARK = env("WATERMARK", "1") == "1"
# HOOK OVERLAY: teks hook besar di 2-3 detik pertama klip.
HOOK_OVERLAY = env("HOOK_OVERLAY", "1") == "1"
# SFX: whoosh sintesis (awal klip & jahitan jump-cut) + pop saat hook muncul.
SFX = env("SFX", "1") == "1"
SFX_VOLUME = float(env("SFX_VOLUME", "0.3"))
# KURASI OTAK: momen di bawah skor ini TIDAK PERNAH jadi klip —
# "berdaging tapi datar" ditolak, daripada banyak tapi membosankan.
MIN_CLIP_SCORE = float(env("MIN_CLIP_SCORE", "6.0"))
# ============ 5 OTAK SPESIALIS: ruang kerja terpisah per-tugas ============
# Tempel hingga 5 kunci Gemini (dipisah koma): kurator/verifikator/penulis/
# direktur masing-masing dipegang otak BERBEDA yang jalan PARALEL — atensi
# tak terbagi-bagi, kuota tak rebutan, verifikasi 2-tahap aktif.
# Kosong = mode 1-otak lama (pakai GEMINI_API_KEY) — perilaku IDENTIK 100%.
BRAIN_KEYS = [k.strip() for k in env("BRAIN_KEYS", "").split(",") if k.strip()]
BRAIN_MODE = env("BRAIN_MODE", "auto")  # auto (multi bila >=2 kunci) | off | multi
BGM_DIR = BASE_DIR / "bgm"

# ============ URL CHANNEL/PROFILE (auto-deteksi, semua platform yt-dlp) ============
# Tempel link channel/profile/playlist -> sistem memilih video TERBAIK dari
# CHANNEL_MAX_CANDIDATES entri terbaru: diperhitungkan dari popularitas
# (views) x kesesuaian durasi-untuk-klip x posisi terbaru — bukan random.
CHANNEL_MAX_CANDIDATES = int(env("CHANNEL_MAX_CANDIDATES", "60"))

# ============ PEMBICARA AKTIF (dukungan 2..10+ orang, anti kacau) ============
# Ganti fokus hanya kalau pembicara baru MENAHAN bicara >= SPEAKER_SWITCH_SEC
# (balasan singkat "oke"/"ya"/anggukan < ini = backchannel -> DIABAIKAN).
# Bicara serempak: pindah hanya kalau JELAS lebih dominan (SPEAKER_DOMINANCE x).
SPEAKER_SWITCH_SEC = float(env("SPEAKER_SWITCH_SEC", "1.5"))
SPEAKER_DOMINANCE = float(env("SPEAKER_DOMINANCE", "1.4"))
SPEAKER_MIN_ACTIVITY = float(env("SPEAKER_MIN_ACTIVITY", "0.0035"))  # ambang mulut aktif
SPEAKER_HOLD_SEC = float(env("SPEAKER_HOLD_SEC", "2.0"))  # tenang minimal sesudah pindah fokus (serempak tak flip-flop)        # rotasi hue hangat (derajat) -> rona
# kemerahan kulit ala subsurface scattering; filter hue = paling murah (ovh ~5%)

# OTAK MULTIMODAL: kirim cuplikan frame ke Gemini supaya bisa "melihat" video
BRAIN_MULTIMODAL = env("BRAIN_MULTIMODAL", "1").lower() in ("1", "true", "on")
BRAIN_FRAME_INTERVAL = float(env("BRAIN_FRAME_INTERVAL", "8"))  # 1 frame tiap N detik
BRAIN_MAX_FRAMES = int(env("BRAIN_MAX_FRAMES", "48"))
X264_PRESET = env("X264_PRESET", "veryfast")  # mau kualitas++: "medium" (lebih lambat)
X264_CRF = env("X264_CRF", "20")
