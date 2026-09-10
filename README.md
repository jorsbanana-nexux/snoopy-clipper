# 🎬 Snoopy Clipper

AI web clipper **sederhana & bersih** — 1 otak (Gemini), input URL, keluar shorts vertikal 9:16 siap download.
Dibuat untuk PC low-spec: prioritas #1 adalah **kamu tidak menunggu lama** (ETA realtime + koreksi otomatis).

> **Coba tanpa setup di PC:** buka [`colab_test.ipynb`](colab_test.ipynb) di Google Colab
> (File → Upload notebook, atau jalankan via [colab.research.google.com](https://colab.research.google.com)) —
> clone, install, uji pipeline penuh, dan preview hasil klip langsung di notebook. Cukup siapkan API key Gemini.
> Mode **URL** (YouTube/TikTok/IG) atau **UPLOAD** file mp4 sendiri (kebal blokir YouTube di server Colab).

---

## 📖 Daftar Isi

1. [Alur Kerja dari Sisi Pengguna](#alur-kerja-dari-sisi-pengguna)
2. [Fitur Lengkap](#fitur-lengkap)
3. [Arsitektur & Pipeline Detail](#arsitektur--pipeline-detail)
4. [Peta Kode & Cara Memodifikasi](#peta-kode--cara-memodifikasi)
5. [Keputusan Desain & Hasil Benchmark](#keputusan-desain--hasil-benchmark)
6. [Panduan Setup Step-by-Step](#panduan-setup-step-by-step)
7. [Referensi Konfigurasi (.env)](#referensi-konfigurasi-env)
8. [FAQ & Troubleshooting](#faq--troubleshooting)
9. [Roadmap](#roadmap)

---

## Alur Kerja dari Sisi Pengguna

```
1. Buka http://localhost:8000
2. Tempel URL video (YouTube, TikTok, IG, dll) di satu-satunya kolom input
3. Klik tombol [GetClips]
4. Pantau progress: tiap langkah + sisa waktu (ETA) terlihat realtime
5. Selesai → library klip muncul: preview langsung + tombol [Download MP4]
   (semua sudah include: potongan presisi, face tracking, subtitle MrBeast-style,
    grade ultra, motion blur, 9:16 1080x1920)
```

Video yang sama tidak diproses dua kali — download, audio, dan cuplikan frame di-cache di folder `downloads/`.

---

## Fitur Lengkap

| Fitur | Detail |
|---|---|
| **1 otak AI** | Gemini (gratis tier cukup). Satu-satunya layanan eksternal. |
| **ETA jujur + kalibrasi drift** | Mesin ETA total (_estimates/_left) kini DIPASANG: fase unduh/frame/otak menampilkan sisa-waktu total, transkrip menghitung sisa (whisper+frame+otak) bukan whisper saja. Setelah tiap klip dirender, kecepatan NYATA mengkalibrasi estimasi klip berikutnya — ETA makin akurat sepanjang job. |
| **Kredit BGM tampil di UI** | Lisensi CC-BY Incompetech dipatuhi: kredit per klip (dari meta.json) tampil di kartu klip di library. |
| **URL channel/profile/playlist (semua platform)** | Tempel link channel YouTube (`@handle`, `/channel/`, `/user/`) atau profile platform lain — sistem otomatis memilih video TERBAIK dari kandidat terbaru: diperhitungkan dari popularitas (views) × kesesuaian durasi-untuk-klip × posisi terbaru. Live/upcoming & kurang layak disaring, alasannya tampil di UI — bukan random, bukan asal ambil. |
| **Pembicara aktif v4 — kelas profesional (1..10+ orang)** | Kamera sadar UCAPAN: gerak mulut dihitung bicara hanya saat Whisper mendengar ucapan (ketawa/nyengir saat jeda tak pernah mencuri kamera). Identitas wajah dijaga matching velocity (aman saat 10 orang bersilangan jalan). Dominasi dinilai dari rata-rata segmen + tenang minimal 2 dtk setelah pindah — tanpa flip-flop. Sampling 0.5 dtk: reaksi 2× lebih gesit. Margin wajah anti "setengah badan". |
| **Pembicara aktif (2..10+ orang)** | Kamera fokus ke PEMBICARA AKTIF: ganti fokus hanya saat pembicara baru menahan bicara ≥1,5 dtk (balasan singkat "oke"/"ya" diabaikan), bicara serempak hanya pindah kalau jelas lebih dominan (1,4×) — kamera tenang & mulus, tidak flip-flop. Matching wajah global-jarak menjaga identitas walau banyak wajah rapat. Pembicara hilang dari frame → serahkan mulus ke wajah dominan. |
| **BGM viral otomatis** | Otak menentukan mood tiap klip (comedy/upbeat/epic/tension/mystery/emotional/chill/action) di panggilan yang sama → BGM profesional Kevin MacLeod (CC BY 4.0) dicampur volume rendah 15% + fade halus. Track diunduh SEKALI lalu cache permanen (mono ~0.5-1.5MB) — nol unduhan per klip. **BGM wajib selalu ada**, tidak pernah kosong. Kredit tersimpan otomatis (meta.json + `description.txt`). |
| **Otak ELITE v4** | Gemini (model tertinggi duluan, turun otomatis) menerima **judul + channel + transkrip + frame** → berpikir KONTEKS DULU → menilai seperti penonton acak → PILIH dengan standar editor legendaris (retensi 2 dtk, curiosity gap, trigger share/save, hanya momen score 7+). **Jumlah klip = keputusan otak sesuai kualitas video** (bukan kuota tetap). SATU panggilan — nol langkah ekstra. |
| **Semua platform** | Apapun yang didukung yt-dlp: YouTube, TikTok, Instagram, X, Facebook, dll. URL **YouTube Kids otomatis dinormalisasi** + **deteksi video anak** (URL kids / judul khas) → otak masuk mode aman anak (momen lucu/edukatif, framing hangat). |
| **Momen berdaging** | Prompt ketat 3-langkah terlatih: PAHAMI DULU → nilai sebagai penonton acak → konteks → membangun → pay-off. Adaptif jenis konten (podcast/gaming/storytime/edukasi/anak). Basa-basi/iklan/momen asal ditolak. |
| **Potongan presisi** | Start/end di-snap ke timestamp kata asli (toleransi 2 dtk) + seek akurat frame-level — tak lebih, tak kurang. |
| **Face tracking v2** | Semua wajah di-track; "siapa bicara" dari gerakan mulut (window ±2 sampel — gesit); hysteresis anti flip-flop; **look-ahead S-curve C1** (transisi smoothstep mulus antar pembicara, kamera tiba ~saat pembicara baru mulai bicara); kecepatan pan di-clamp; **pan interpolasi KUBIK Catmull-Rom — kecepatan kontinu per-frame, tanpa 'macet skala kecil'**. |
| **Smart Placement v4** | Subtitle tidak pernah menutupi: wajah/objek utama (collision bbox, geser atas kepala/bawah dagu), UI platform (safe zone kanan & bawah ala TikTok/Reels), teks bawaan video (deteksi baris teks — pengganti OCR ringan), dan area saliency (objek menarik mata dihindari). Semua numpang di pass sampling wajah = biaya nyaris nol. |
| **Subtitle premium v3** | Font **Komika Axis**, Huruf Besar Di Awal, teks bersih tanpa titik/koma, **kata muncul satu-satu saat diucapkan (pop + bounce)**, **KARAOKE STABILO biru MrBeast**: kata yang sedang diucapkan biru, selesai → putih, biru berjalan mengikuti ucapan terus-menerus, ukuran wajar & posisi bawah layar (ala Opus/snazo), naik otomatis kalau menutupi wajah. |
| **Grade "Ultra Settings"** | eq (bayangan pekat) + hue (kulit hangat) + unsharp 3x3 (texture tajam) — dipilih dari benchmark biaya CPU. |
| **Motion blur ala game** | Aktif HANYA saat kamera pan (tmix), halus, subtitle tetap tajam. |
| **Output** | MP4 9:16, 1080x1920 (auto 720x1280 kalau sumber kecil), H.264 + AAC, auto-detect encoder GPU. |
| **ETA realtime** | Estimasi per langkah, dikoreksi otomatis dari kecepatan aktual PC-mu → makin lama makin akurat. |
| **Thumbnail otomatis WAJIB (default NYALA)** | Setiap klip PASTI punya thumbnail .jpg 1080x1920 — tidak pernah gagal/hilang: rantai fallback 4 lapis (frame wajah terbaik → frame terpajam → frame klip jadi → kartu gradient). Pemilihan frame ala thumbnail profesional: wajah terbesar + mulut terbuka (ekspresi = klik) + ketajaman + exposure waras; crop 9:16 wajah di 40% atas + grade kontras/saturasi/unsharp sama selera klip. TANPA teks → netral semua bahasa (teks = fase 2). Disajikan via `/api/thumbs/<video>/<clip>` + kolom `thumb` di meta; UI/frontend cukup baca meta.json. |
| **Diarization (opsional, default MATI)** | Label pembicara per baris transkrip (pyannote, CPU) → otak tahu SIAPA bicara apa. Monolog otomatis diabaikan (label dibuang). Gagal apa pun (token/library tidak ada) → job jalan normal tanpa label, tidak pernah error. Setup: `pip install -r requirements-diarize.txt`, akun HuggingFace gratis + accept license model, lalu `.env`: `DIARIZE=1` dan `DIARIZE_TOKEN=hf_xxx`. |

---

## Arsitektur & Pipeline Detail

```
                              ┌──────────────────────────────────────────┐
 URL video ──► [GetClips] ──► │  PIPELINE (backend/pipeline.py)          │
                              │  antrean 1 job sekaligus (CPU aman)      │
                              └───────────┬──────────────────────────────┘
                                          │
   ① INFO      ──────────────────────────► downloader.get_info()      → judul, durasi, id
   ② DOWNLOAD  ─────────────────────────► downloader.download()       → downloads/<id>.mp4 (cache)
   ③ AUDIO     ─────────────────────────► cutter.extract_audio()      → wav 16kHz mono (cache)
   ④ TRANSCRIBE ───────────────────────► transcriber.transcribe()     → teks + timestamp PER KATA
   ⑤ FRAMES    ─────────────────────────► cutter.extract_frames()     → cuplikan jpg (cache, utk otak)
   ⑥ OTAK      ─────────────────────────► brain.find_moments()        → Gemini: transkrip + frame
   │                                                                        → momen berdaging + batas presisi
   ⑦ per klip: ┌──────────────────────────────────────────────────────┐
   │           │ facetrack.track()  → keyframe pan + posisi wajah      │
   │           │ subtitles.build_ass() → subtitle MrBeast (ASS)        │
   │           │ cutter.render_clip() → 1 PASS ffmpeg:                 │
   │           │   crop 9:16 (pan ikut wajah) → scale 1080x1920       │
   │           │   → grade ultra (eq→hue→unsharp) → motion blur       │
   │           │   → burn subtitle → encode H.264 + AAC                │
   │           └──────────────────────────────────────────────────────┘
   ⑧ LIBRARY   ─────────────────────────► library.save_meta()          → library/<id>/clip_XX.mp4
                                        │                              + meta.json
                                        ▼
                          GET /api/clips/<video>/<clip> → preview & download
```

### Penjelasan tiap langkah

**① Info** — `yt-dlp` baca metadata tanpa download (±3 dtk). Durasi dipakai untuk menghitung ETA awal.

**② Download** — unduh video maksimal `MAX_SOURCE_HEIGHT` (default 1080) lalu merge jadi mp4. File di-cache: video sama tidak diunduh ulang.

**③ Audio** — ekstrak wav 16kHz mono. Whisper cuma butuh audio, jadi ini bikin transkrip jauh lebih cepat daripada membaca video.

**④ Transkripsi** — `faster-whisper` model `small`, compute `int8`, CPU, beam 5. Menghasilkan **timestamp per kata** (word-level) — kunci dari potongan presisi, subtitle per kata, dan reveal satu-satu. Anti-typo: VAD membuang keheningan + `condition_on_previous_text=False` mencegah typo berulang/drift saat pembicara cepat.

**⑤ Cuplikan frame** — 1 frame tiap ±8 detik (maks `BRAIN_MAX_FRAMES`), dikecilkan ke 320px, disimpan sebagai jpg. Di-cache. Ini "mata" untuk otak. Matikan dengan `BRAIN_MULTIMODAL=0` kalau mau tercepat.

**⑥ Otak ELITE v4 (Gemini)** — `brain.py` mengirim: (a) **konteks video: judul + channel + mode anak (deteksi otomatis)**, (b) transkrip berformat `[12.4-15.6] teks per baris`, (c) semua frame jpg dalam urutan waktu. Prompt 3-langkah terlatih: **PAHAMI DULU** (topik, siapa saja, di mana dagingnya — mis. judul "pencurian mobil" → cari bagian kisahnya diberi tahu detail) → **NILAI SEBAGAI PENONTON ACAK** (bagian mana yang bikin kaget/emosi/penasaran) → **PILIH** dengan aturan ketat: utuh & berdaging (konteks → membangun → pay-off), start tepat di kalimat yang bikin konteks langsung jelas (contoh: "John, kenapa mobilmu bisa dicuri?"), adaptif jenis konten, 15–90 dtk, anti tumpang tindih, judul + hook + score jujur. Jumlah momen FLEKSIBEL: pilih SEMUA yang layak (score 7-10) — bisa 3, bisa 30, plafon `MAX_CLIPS`=100 hanya pengaman. Jawaban JSON (`{analysis, moments}`) divalidasi: snap ke batas kata terdekat, clamp durasi, buang tumpang tindih, sort by score. Semua dalam SATU panggilan Gemini — waktu proses tidak berubah.

**⑦ Render per klip (satu pass)** —
- *Face tracking* (`facetrack.py`): YuNet mendeteksi **semua** wajah + landmark mulut tiap 1 dtk **hanya di area klip**. Wajah dipairing antar frame jadi track; "siapa bicara" dinilai dari variance gerakan sudut mulut; pilihan fokus diberi **hysteresis** (anti flip-flop). Transisi antar pembicara = **S-curve smoothstep (C1 di kedua ujung)** yang ditanam sebelum smoothing + antisipasi lag deteksi → kamera tiba ~tepat saat pembicara baru mulai bicara, tanpa teleport dan tanpa meninggalkan pembicara lama kepotong setengah wajah. Path dipolish: EMA zero-phase ringan + clamp kecepatan; render pakai **interpolasi kubik Catmull-Rom** (kecepatan kontinu di tiap titik — interpolasi linear membuat kecepatan melompat di tiap keyframe, terlihat sebagai pan 'macet-macet kecil').
- *Smart placement* (`placement.py`): sebelum render, ukuran bounding box teks dihitung dari jumlah huruf & ukuran font, lalu posisi dipilih dari kandidat di sekitar posisi ideal (±70% tinggi frame) dengan skor penalti: tabrakan dengan bounding box wajah (paling besar), tumpang tindih teks bawaan video, area saliency (objek menarik mata), dan jarak dari posisi ideal — plus safe zone platform (kanan 12% utk tombol like/share, bawah 15% utk username/deskripsi). Semua data vision diambil dari pass sampling wajah yang sama (biaya tambahan nyaris nol — tanpa MediaPipe/YOLO/EasyOCR yang berat di PC low-spec).
- *Subtitle* (`subtitles.py`): dibangun dari kata-kata di klip. Teks dibersihkan (tanpa titik/koma) + Huruf Besar Di Awal, tiap kata muncul saat diucapkan (alpha pop-in) + bounce overshoot 118%, **karaoke stabilo**: kata aktif **biru MrBeast** selama diucapkan lalu kembali putih — biru berjalan kata-demi-kata mengikuti ucapan, posisi dari smart placement, wrap 2 baris untuk frasa panjang.
- *Encode* (`cutter.py`): satu perintah ffmpeg: `crop` (posisi x mengikuti expression keyframe) → `scale` → `eq` (kontras/gamma/saturasi) → `hue` (rona kulit hangat) → `unsharp 3x3` (luma saja) → `tmix` (motion blur, hanya aktif saat pan cepat) → `ass` (burn subtitle) → H.264 (GPU kalau ada, kalau tidak x264 veryfast) + AAC.

**⑧ Library** — klip disimpan `library/<video_id>/clip_01.mp4` dst + `meta.json` (judul, skor, hook, dll). Frontend mem-polling `GET /api/jobs/{id}` untuk progress, lalu `GET /api/library` untuk grid klip.

---

## Peta Kode & Cara Memodifikasi

> Prinsip: **satu file = satu keputusan desain.** Mau ubah sesuatu? Edit satu tempat yang benar.

| File | Tanggung Jawab | Mau ubah apa? |
|---|---|---|
| `backend/config.py` | SEMUA setting (baca `.env`) | Override apapun tanpa sentuh kode |
| `backend/downloader.py` | Unduh semua platform + cache | Tambah platform / kualitas unduhan |
| `backend/transcriber.py` | Whisper → teks + timestamp per kata | Ganti model whisper / bahasa |
| `backend/brain.py` | **OTAK**: prompt multimodal + validasi momen | Ubah gaya pemilihan momen, model Gemini |
| `backend/facetrack.py` | Tracking v2: track wajah, deteksi pembicara, look-ahead, path mulus | Haluskan tracking / logika fokus |
| `backend/subtitles.py` | Style subtitle v3.1 + integrasi placement | Warna, ukuran, animasi |
| `backend/placement.py` | **Smart Placement**: safe zone UI, collision wajah/teks-bawaan, saliency | Logika posisi subtitle |
| `backend/cutter.py` | Grade, motion blur, ekstraksi frame/audio, encode | Filter visual / encoder |
| `backend/pipeline.py` | Orkestrasi langkah + progress + ETA | Tambah/hapus langkah pipeline |
| `backend/library.py` | Penyimpanan klip + metadata | Format library / export |
| `backend/main.py` | API + serve frontend | Endpoint baru |
| `tests/test_e2e_mock.py` | Uji end-to-end pipeline penuh (otak Gemini di-mock) | Verifikasi setelah ubah pipeline |
| `colab_test.ipynb` | Test drive satu-klik di Google Colab | Demo tanpa PC |
| `frontend/` | UI vanilla (tanpa build step) | Tampilan |

Struktur folder runtime (auto-dibuat, masuk `.gitignore`):
```
downloads/   cache: video mp4, audio wav, cuplikan frame
library/     hasil akhir: clip_XX.mp4 + meta.json per video
jobs/        progress job sementara + file kerja render
models/      model onnx YuNet + mask (auto-download)
```

---

## Keputusan Desain & Hasil Benchmark

Semua pilihan visual/performa dipilih dari **pengukuran nyata**, bukan selera:

| Opsi | Overhead render | Keputusan |
|---|---|---|
| `eq` (kontras/gamma/sat) | ~4% | ✅ dipakai — "Shadow Quality Ultra" |
| `hue` (rona hangat) | ~5% | ✅ dipakai — kulit hangat ala subsurface scattering |
| `unsharp 3x3` | ~62% | ✅ dipakai — "Texture Quality Ultra", termurah di kelasnya |
| `unsharp 5x5` | ~113% | ❌ ditolak — mahal |
| `cas` (sharpen AMD) | ~121% | ❌ ditolak — lebih berat dari unsharp 3x3 |
| `lutrgb` | ~77% | ❌ ditolak — hue jauh lebih murah |
| `colorbalance` | ~303% | ❌ ditolak — sangat mahal di CPU |

Analisis gaya subtitle (bedah 920 frame video tutorial MrBeast):
- **kata muncul satu-satu** saat diucapkan → progressive reveal ✅ diadopsi
- **48% kata dalam keadaan scale-up** → bounce overshoot per kata ✅ diadopsi
- warna isi **putih** + **karaoke stabilo biru** pada kata yang sedang diucapkan ✅ diadopsi (biru → putih, mengikuti ucapan)
- tinggi kata raksasa ±8% & posisi ±74% → ❌ TIDAK diadopsi untuk clipper; dinormalisasi ke ukuran wajar (±4.7%) dan posisi bawah layar (±80%) ala Opus/snazo — font raksasa cocok untuk video MrBeast sendiri, terlalu besar untuk klip berisi wajah + informasi

Keputusan lain:
- **faster-whisper small int8** di CPU: keseimbangan terbaik kecepatan/kualitas untuk low-spec (naikkan ke `medium` kalau PC kuat).
- **YuNet** face detector: onnx ringan, berjalan di resolusi inferensi 192x144.
- **1 job antre sekaligus**: CPU low-spec tidak tersedak; ETA tetap jujur karena antrean kelihatan.
- **Seek `-ss` sebelum `-i`**: frame-akurat saat transcode (potongan pas, tidak mulai dari keyframe terdekat).

---

## Panduan Setup Step-by-Step

### Prasyarat
- **Python 3.10+** — cek: `python --version`
- **ffmpeg** di PATH:
  - Windows: `winget install ffmpeg` (atau download dari ffmpeg.org, tambah ke PATH)
  - Linux: `sudo apt install ffmpeg`
  - cek: `ffmpeg -version`

### Langkah
```bash
# 1. Clone
git clone https://github.com/jorsbanana-nexux/snoopy-clipper.git
cd snoopy-clipper

# 2. (Opsional tapi disarankan) virtual environment
python -m venv .venv
# Windows: .venv\Scripts\activate    |    Linux/Mac: source .venv/bin/activate

# 3. Install dependensi
pip install -r requirements.txt

# 4. Konfigurasi — WAJIB isi API key Gemini (gratis)
cp .env.example .env
# edit .env, isi: GEMINI_API_KEY=... (ambil di https://aistudio.google.com/apikey)

# 5. Jalankan server
uvicorn backend.main:app --host 0.0.0.0 --port 8000

# 6. Buka browser
# http://localhost:8000
```

### Pemakaian pertama
Saat job pertama jalan, model **YuNet onnx (±1 MB)** otomatis terunduh ke `models/`, dan model whisper `small` (~460 MB) otomatis terunduh sekali oleh faster-whisper. Job berikutnya jauh lebih cepat.

---

## Referensi Konfigurasi (.env)

Semua bisa diubah tanpa sentuh kode. Kosongkan/gunakan nilai default kalau ragu.

### Otak & transkripsi
| Setting | Default | Keterangan |
|---|---|---|
| `GEMINI_API_KEY` | — | **WAJIB**. Gratis di aistudio.google.com/apikey |
| `GEMINI_MODEL` | gemini-3.1-pro-preview | Model otak — tertinggi duluan; kalau bermasalah otomatis turun ke `GEMINI_FALLBACK_MODELS` (urutan dari yang paling tinggi) |
| `WHISPER_MODEL` | small | tiny/base lebih cepat, medium lebih akurat |
| `WHISPER_BEAM` | 1 | Beam search — 1 = tercepat (ketepatan waktu kata tetap, dari alignmen audio); 5 = anti-typo maksimal |
| `WHISPER_COMPUTE` | int8 | Paling ringan di CPU |
| `BRAIN_MULTIMODAL` | 1 | 0 = otak analisis teks saja (lebih cepat) |
| `BRAIN_FRAME_INTERVAL` | 8 | 1 frame tiap N detik utk dilihat Gemini |
| `BRAIN_MAX_FRAMES` | 48 | Batas jumlah frame per request |

### Pemilihan momen
| Setting | Default | Keterangan |
|---|---|---|
| `MAX_CLIPS` | 100 | Plafon pengaman saja — jumlah klip ditentukan otak AI sesuai kualitas video |
| `MIN_CLIP_SEC` | 15 | Durasi klip minimum |
| `MAX_CLIP_SEC` | 90 | Durasi klip maksimum |

### Output & kecepatan (low-spec)
| Setting | Default | Keterangan |
|---|---|---|
| `FORCE_RESOLUTION` | auto | `720` = render tercepat; `1080` = paksa full HD |
| `MAX_SOURCE_HEIGHT` | 1080 | Turunkan ke `720` → unduh & render jauh lebih cepat |
| `X264_PRESET` | veryfast | `medium` = kualitas naik, lebih lambat |
| `X264_CRF` | 20 | Kecil = tajam & file besar |
| `FACE_SAMPLE_INTERVAL` | 1.0 | Detik antar sampel wajah (0.5 = lebih responsif) |
| `LEAD_AHEAD_SEC` | 2.0 | Kamera menyorot duluan sebelum ganti pembicara |

### Visual
| Setting | Default | Keterangan |
|---|---|---|
| `GAME_ULTRA` | 0 | Efek game tetap jalan di 0; 1 = grade paling rame, render +40% |
| `BGM` | 1 | 1 = BGM otomatis per klip; 0 = matikan |
| `BGM_VOLUME` | 0.15 | Intensitas BGM (15% dari suara utama — kecil & nyaman) |
| `SPEAKER_SWITCH_SEC` | 1.5 | Lama menahan bicara sebelum pembicara baru boleh merebut fokus (interjeksi singkat diabaikan) |
| `SPEAKER_DOMINANCE` | 1.4 | Rasio dominasi saat dua+ orang bicara serempak (anti flip-flop) |
| `SPEAKER_HOLD_SEC` | 2.0 | Tenang minimal sesudah pindah fokus (serempak tidak flip-flop) |
| `CHANNEL_MAX_CANDIDATES` | 60 | Jumlah kandidat terbaru yang dinilai saat URL channel/profile ditempel |
| `UNSHARP_AMOUNT` | 0.45 | Ketajaman tekstur (0 = off) |
| `EQ_CONTRAST` / `EQ_GAMMA` / `EQ_SATURATION` | 1.06 / 0.94 / 1.12 | Bayangan pekat + warna hidup |
| `WARM_HUE_DEG` | 2.0 | Rona kulit hangat (derajat) |
| `MOTION_BLUR` | 1 | 0 = matikan motion blur |
| `MOTION_BLUR_STRENGTH` | 0.35 | 0.1–0.5, kecil = halus |

### Subtitle (MrBeast v3)
| Setting | Default | Keterangan |
|---|---|---|
| `SUBTITLE_FONT` | Komika Axis | Wajib install font Komika Axis di sistem |
| `SUBTITLE_CASE` | title | `title` = Huruf Besar Di Awal; `upper`; `normal` |
| `SUBTITLE_SIZE_FRAC` | 0.047 | Ukuran wajar ±4.7% tinggi frame |
| `SUBTITLE_Y_FRAC` | 0.70 | Posisi ideal (60-75% = area paling bersih dari UI platform) |
| `PLACEMENT_SMART` | 1 | 0 = matikan smart placement (posisi fixed) |
| `UI_SAFE_RIGHT` | 0.12 | Zona aman kanan (tombol like/comment/share) |
| `UI_SAFE_BOTTOM` | 0.15 | Zona aman bawah (username/deskripsi) |
| `SUBTITLE_MIN_Y_FRAC` | 0.18 | Batas atas posisi subtitle |
| `SUBTITLE_POP` | 1.18 | Overshoot bounce tiap kata |
| `SUBTITLE_POP_MS` | 80 | Durasi pop (ms) |
| `HIGHLIGHT_COLOR` | FFAA00 | Biru stabilo karaoke MrBeast (#00AAFF, format BGR ASS) |
| `KARAOKE_FADE_MS` | 70 | Kecepatan transisi warna biru↔putih (ms) |

---

## FAQ & Troubleshooting

**Kok lama?** Cek langkah mana yang lambat di progress bar, lalu:
- Transkripsi lambat → `WHISPER_MODEL=base`
- Download lambat → `MAX_SOURCE_HEIGHT=720`
- Render lambat → `FORCE_RESOLUTION=720`, `GAME_ULTRA=0`, `MOTION_BLUR=0`

**"Tidak ada ucapan terdeteksi"** — videonya minim bicara; otak butuh transkrip.

**Font Komika Axis belum terpasang** — download gratis (cari "Komika Axis font"), install ke sistem (Windows: klik kanan .ttf → Install; Linux: copy ke ~/.fonts lalu `fc-cache -f`). Kalau tidak ada, libass otomatis pakai font lain.

**Subtitle masih typo pada pembicara cepat/audio berisik** — naikkan `WHISPER_BEAM=5` dan coba `WHISPER_MODEL=medium` kalau PC kuat. Default 1 = tercepat; kualitas waktu kata tidak terpengaruh beam. Pipeline sudah memakai anti-drift (`condition_on_previous_text=False`) + VAD.

**Gemini error 429** — free tier kena limit; tunggu sebentar — rantai fallback otomatis turun ke model berikutnya, atau ganti `GEMINI_MODEL`.

**Hasil tracking kaku di video X** — turunkan `FACE_SAMPLE_INTERVAL` ke 0.5 dan ceritakan detik mana yang bermasalah (masalah spesifik lebih mudah diperbaiki daripada kesan umum).

**PC nge-freez saat render** — pastikan tidak ada job lain jalan; pipeline sudah antre 1 job sekaligus, tapi browser preview 1080x1920 juga makan RAM.

---

## Uji Tanpa PC (Google Colab)

`colab_test.ipynb` menjalankan pipeline penuh di Colab: setup otomatis, API key Gemini via Secrets/input,
video via URL atau upload file, progress + ETA live, preview klip inline + ZIP unduhan.
Cocok untuk: coba pertama kali, demo, atau uji perubahan tanpa repot PC low-spec.
( Pipeline lokal & Colab pakai kode yang sama persis dari repo ini. )

## Deploy ke VPS (siap publik)

Server ini bisa dititipkan di VPS murah mana pun (butuh ~2 GB RAM):

```bash
cp .env.example .env
# isi GEMINI_API_KEY, lalu GENERATE kunci akses:
python3 -c "import secrets; print(secrets.token_urlsafe(24))"   # -> API_KEY=
docker compose up -d --build
```

Yang sudah ada di lapisan siap-produk:
- **API_KEY** (.env) — tanpa ini, server publik = orang asing pakai Gemini
  key & CPU kita gratis. Frontend otomatis minta kunci sekali per browser.
- **DAILY_MINUTES_LIMIT** (.env) — kuota menit video per hari (reset 00:00 UTC),
  fondasi billing. Job GAGAL tidak menghabiskan kuota.
- **Pemulihan job basi** — server restart/crash saat job jalan: job otomatis
  ditandai error yang jelas saat server hidup lagi, tidak nanggung "running".
- **logs/jobs.log** — JSONL ringan (start/done/error + durasi) + `GET /api/stats`
  (jumlah job, klip, rata-rata detik per job) & `GET /api/quota`.

Belum ada (roadmap): login multi-user penuh, pembayaran, auto-post ke platform.

## Roadmap

- [ ] Test drive di video nyata → kalibrasi rasa (grade & tracking)
- [ ] Prompt otak v3: contoh few-shot per genre (gaming/podcast/vlog)
- [x] Smart placement subtitle (wajah, UI safe zone, teks bawaan, saliency) ✅ selesai
- [ ] Deteksi hype audio (tawa/aplause) sebagai sinyal skor momen
- [ ] Export langsung ke platform (YouTube Shorts API, TikTok)
- [ ] Queue antar-video di UI

---

* dibangun dengan prinsip: bersih, 1 file = 1 tanggung jawab, semua keputusan terukur — supaya agent masa depan (atau kamu) bisa lanjut mengembangkannya tanpa membuka kotak hitam.*
