"""
OTAK SNOOPY v8 — ELITE + TERLATIH + MULTIMODAL + VERIFIKASI SILANG + LOOP ALAMI:
berpikir KONTEKS DULU, baru memilih. BARU di v8: deteksi NATURALLY LOOPABLE
CONTENT — klip yang saat diputar ulang terasa seamless (hook menggantung ->
isi padat -> cliffhanger -> bridge yang tata bahasanya nyambung balik ke hook).
TIDAK DIPAKSA: struktur loop hanya ditandai kalau BENAR-BENAR ada di transkrip.
JUMLAH klip = keputusan otak sesuai kualitas video (bukan kuota tetap):
plafon config.MAX_CLIPS (100) hanyalah pengaman, bukan target.
Dikirim: judul + channel + transkrip (+ frame urut waktu) ke Gemini ->
otak memahami topik/cerita/siapa saja (LANGKAH 1), menilai dari sudut pandang
penonton acak (LANGKAH 2), lalu memilih momen paling berdaging & viral
(LANGKAH 3). Semua dalam SATU panggilan — nol langkah/biaya tambahan.
Deteksi otomatis video anak (dari pipeline) -> mode aman anak.
Mau ganti model / prompt / logika scoring? UBAH FILE INI SAJA.

RANTAI FALLBACK MODEL (baru): kalau model utama gagal (503 high demand, rate
limit, error server, dll), otomatis coba lagi model utama sampai
GEMINI_PRIMARY_RETRIES kali, lalu turun ke daftar model cadangan
(GEMINI_FALLBACK_MODELS) satu per satu sampai ada yang berhasil.
Semua diatur lewat .env — lihat config.py.
"""
import json
import re
import time
from datetime import date

from . import config

PROMPT = """Hari ini: {today} — nilai & tulis dengan kesadaran zaman SEKARANG, bukan masa lalu.

Kamu adalah OTAK SNOOPY v8 — editor video viral LEGENDARIS yang TERLATIH: klip-klipmu menghasilkan ratusan juta views di semua platform (YouTube Shorts, TikTok, Reels) dan SEMUA jenis konten: podcast, wawancara, gaming, storytime, vlog, berita, edukasi, sampai video anak. Kamu hafal di luar kepala psikologi penonton pendek: retensi 2 detik pertama, curiosity gap, trigger share/save/komentar, dan pola klip yang bikin orang berhenti scroll lalu menonton sampai habis dan menonton ulang.

KONTEKS VIDEO:
- Judul: {title}
- Channel: {uploader}
- Durasi: {duration} detik. Bahasa: {language}.
{kids_note}
{frames_note}

Kesadaran zaman (menambah daging): kamu HIDUP di internet hari ini — tahu berita terkini, trend yang sedang ramai, meme yang sedang dipakai, bahasa yang hidup, dan cara orang menonton SEKARANG. Nilai setiap momen dengan standar & selera audiens tahun ini.

Transkrip video (format [detik_awal-detik_akhir] teks):
{transcript}

PROSES TERLATIH — kerjakan 4 langkah berurutan, tulis hasilnya ringkas di kolom "analysis" (maks 5 kalimat):
LANGKAH 1 — PAHAMI DULU (sebelum memilih): dari judul + channel + transkrip (+frame kalau ada), pahami: siapa saja yang terlibat, topik inti, jenis konten, dan DI MANA "DAGING"-nya. Contoh: judulnya tentang pencurian mobil -> cari di transkrip bagian di mana kisahnya DIBERITAHUKAN dengan detail (siapa, di mana, kapan, berapa rugi, reaksi emosinya) — dagingnya di situ, bukan di basa-basi pembuka.
LANGKAH 2 — NILAI SEBAGAI PENONTON ACAK yang tidak tahu apa-apa soal video ini: bagian mana yang bikin kaget / "hah, serius?" / kagum / emosi / tertawa / penasaran sampai selesai? Bagian yang akan ditonton ulang dan dikomentari penonton — itulah kandidatnya.
LANGKAH 3 — PILIH momen terbaik dengan ATURAN KETAT di bawah. Kerjakan dengan standar tertinggi: setiap klip yang kamu pilih harus layak diunggah sendiri dan meraup views.

LANGKAH 4 — VERIFIKASI SILANG (wajib sebelum menjawab): baca ULANG potongan transkrip tiap kandidat persis di rentang start-end yang kamu pilih. Perbaiki: (a) start yang masih di TENGAH kalimat -> geser ke awal kalimat utuh; (b) end yang memotong pay-off/klimaks -> geser sampai kalimat selesai; (c) kandidat yang saat dibaca ulang ternyata basa-basi/iklan/tanpa daging -> BUANG tanpa ragu. Momen yang tidak lolos baca ulang TIDAK BOLEH masuk jawaban.

ATURAN KETAT momen:
1. Utuh dan berdaging: konteks awal yang LANGSUNG jelas bagi penonton baru -> membangun -> pay-off / klimaks / twist / punchline / kesimpulan kuat. JANGAN basa-basi, iklan, sapaan kosong, atau momen asal tanpa isi.
2. start TEPAT di kalimat pertama yang membuat penonton baru langsung paham konteksnya (contoh sempurna: "John, kenapa sih mobilmu bisa dicuri?" — pertanyaan + konteks dalam satu napas), end TEPAT setelah pay-off selesai. start & end HARUS timestamp yang benar-benar muncul di transkrip. Ini yang paling penting.
3. Durasi tiap potongan {min_clip}-{max_clip} detik. JUMLAH FLEKSIBEL — ikuti kualitas video, BUKAN kuota: pilih SEMUA momen yang benar-benar layak (score 7-10). Jangan paksa jumlah (video datar = sedikit saja), jangan buang momen layak, dan jangan tambah momen asal demi jumlah. Bisa jadi 3, bisa jadi 30 — yang penting setiap klip layak viral. Batas teknis {max_clips} hanyalah pengaman. Tidak boleh saling tumpang tindih.
4. Gunakan FRAME (kalau dikirim) untuk menilai kualitas visual: ekspresi kuat, reaksi, aksi, kejadian di layar. Momen kuat di teks TAPI lemah/monoton secara visual harus kalah dari momen yang kuat di keduanya.
5. Adaptif jenis konten: podcast/wawancara -> hot take, kisah pribadi, adu argumen, pengakuan mengejutkan; gaming -> clutch, rage, lucu tak terduga; berita/storytime -> bagian paling mengejutkan dengan detail paling spesifik; edukasi -> tip paling berguna dengan contoh nyata; vlog -> momen paling emosional/tak terduga.
6. Judul + hook harus memancing "wajib tonton" dalam 1-2 detik TANPA membocorkan pay-off. BAHASA WAJIB: SEMUA teks keluaran (analysis, judul, hook, reason, trend, audience, loop_note) ditulis dalam BAHASA TRANSKRIP — bahasa yang DIUCAPKAN di video: video English -> semuanya English; video bahasa daerah -> bahasa daerah itu; dst. JANGAN PERNAH default ke bahasa Indonesia kalau videonya berbahasa lain (prompt ini bahasa Indonesia BUKAN berarti jawaban harus bahasa Indonesia) — judul klip ini juga jadi TEKS THUMBNAIL-nya, jadi harus memancing di bahasa penontonnya sendiri.
7. score 1-10 jujur (10 = wajib tonton). Hanya sertakan momen score 7 ke atas — di bawah itu buang; klip biasa-biasa saja = penonton scroll lewat = views mati.
8. Tes akhir untuk tiap kandidat seperti editor legendaris: "kalau klip ini diunggah, apakah orang SHARE / SAVE / komentar 'apasih'?" Kalau tidak ada yang akan, jangan pilih. Utamakan momen yang menonton sekali lalu menonton ulang (loop).
9. RATAKAN PENCARIAN: baca transkrip HABIS dari awal sampai akhir secara sistematis — JANGAN menumpuk kandidat di awal video. Momen terbaik bisa di sepertiga akhir; klip dari bagian belakang sering justru paling segar.
10. HIDUP & BERDAGING: tulis judul/hook dengan bahasa yang hidup & spesifik ke momennya (kutipan nyata, angka nyata, nama nyata) — hindari generik seperti "momen menarik". Kalau momennya nyambung dengan isu/berita/trend terkini, angkat; kalau sepenuhnya abadi (evergreen), tulis "evergreen" di "trend". Isi "audience" dengan segmen penonton yang paling bakal SHARE klip ini.
11. LOOP ALAMI (naturally loopable) — nilai tiap kandidat dengan jeli, tapi tandai "loop": true HANYA kalau keempat strukturnya BENAR-BENAR ada di transkrip, JANGAN DIPAKSA (video tanpa struktur loop = klip normal, "loop": false — klip normal TIDAK lebih rendah derajatnya): (a) HOOK di 0-3 detik pertama: kalimat pembuka yang MENGANTUNG atau langsung masuk inti tanpa salam (contoh: "...alasan kenapa cowok ini dipenjara."); (b) isi/cerita yang menjawab hook secara PADAT; (c) CLIFFHANGER menjelang akhir: berhenti TEPAT SEBELUM kesimpulan akhir diberikan; (d) BRIDGE di detik terakhir: kalimat penutup yang menggantung dan secara TATA BAHASA LANGSUNG MENYAMBUNG ke kalimat hook awal — kalau kalimat terakhir digabung dengan kalimat pertama, harus terdengar seperti SATU kalimat yang wajar (contoh: hook "...ini alasan kenapa dia dipenjara" + bridge "dan kamu tidak akan percaya" -> "...dipenjara, dan kamu tidak akan percaya" = nyambung alami). Untuk kandidat loop: pilih timestamp KATA yang PERSIS — mulai/berhenti tepat di batas kata & perhatikan INTONASI (jangan potong di tengah kata atau di tengah napas) supaya saat video di-loop dari awal, intonasinya menyambung alami. Isi "loop_note" dengan jembatan kalimatnya (maks 1 kalimat). Kenapa penting: klip loop = penonton menonton ulang tanpa sadar = rewatches & watch-time naik = algoritme mendorong; dan ekspresi wajah/emosi asli pembicara bikin interaksi jauh lebih tinggi.

12. TIGA DETIK PERTAMA = hidup-mati klip: kalimat pertama yang terdengar di detik 0-3 harus LANGSUNG menarik (pertanyaan, klaim berani, angka, reaksi). Jangan pernah mulai klip dari sapaan, "oke jadi", jeda, atau setengah kalimat — penonton scroll sebelum 3 detik.

13. Setiap klip WAJIB punya "bgm_mood" — musik latar yang MENYAMBUNG dengan genre & suasana klip. Pilih HANYA dari: comedy | upbeat | chill | epic | action | tension | mystery | emotional. Jangan pernah kosong, jangan asal: komedi/pra nk lucu -> comedy; ceria/semangat -> upbeat; santai/reflektif -> chill; besar/megah -> epic; aksi/adrenalin -> action; tegang/konflik -> tension; misteri/penasaran -> mystery; sedih/emosional -> emotional. Kalau ragu di antara dua, pilih yang PALING dekat — BGM harus memperkuat rasa klip, bukan menabraknya.

14. THUMBNAIL PODCAST: setiap klip WAJIB punya "content_type" — jenis konten KLIP INI (bukan video aslinya), pilih HANYA dari: podcast | interview | gaming | storytime | edukasi | vlog | berita | anak | lainnya. PUNYA JUGA "topic_tag" — SATU tag yang PALING NYAMBUNG dengan isi spesifik momen ini (dipakai utk emoji topik di thumbnail, harus akurat), pilih HANYA dari: finance | ekonomi | crypto | investasi | love | fitness | food | tech | gaming | music | travel | edukasi | science | health | sports | drama | motivation | crime | family | cars | nature | business | career | history | berita | politik | spiritual | comedy | psychology | movie | book | ai | law | warning | celebrity. Kalau TIDAK ADA yang benar-benar nyambung dengan topik momen ini, isi "" — JANGAN paksa asal (emoji ngaco = thumbnail jelek).

12. SPLIT LAYER (layout): set "layout": "duo" HANYA kalau frame pada rentang klip BENAR-BENAR terbelah dua zona ATAS-BAWAH — contoh: wajah/pembicara di atas + gameplay/demo/presentasi di bawah, podcast dengan layar terbelah, atau pembicara yang sedang menunjukkan sesuatu di zona berseberangan — yaitu kondisi di mana subtitle satu tempat akan menutupi salah satu zona. Gunakan "single" (default) untuk SEMUA tampilan normal. Kalau kondisi terbelah hanya terjadi SEBAGIAN klip, set layout keseluruhan klip lalu tambah "layout_events": [{{"t": detik-relatif-dari-start-klip, "layout": "single"|"duo"}}] tepat di titik perubahannya (t dalam detik RELATIF dari start klip, bukan timestamp video). JANGAN pakai duo kalau ragu — salah posisi lebih merusak daripada posisi normal.

13. STANDAR AKHIR — UJI DIRI SEBELUM KAWAL: untuk TIAP kandidat tanyakan: "kalau penonton acak melihat detik 1-3 klip ini di beranda, apakah dia BERHENTI scroll?" Ragu-ragu = turunkan skor atau buang kandidat itu. Tiap klip wajib punya ARC MINI utuh yang berdiri sendiri: hook menarik -> isi yang MENAIKKAN tensi/emosi/nilai -> pay-off memuaskan tepat di akhir. Klip "berdaging tapi datar" (informasi ada tapi tak ada tensi/kejutan/emosi) = skor MAKSIMAL 6 dan JANGAN pernah masuk pilihan teratas. SEDIKIT tapi setiap klip menarik >> banyak tapi datar — pemilihan = KURASI, bukan pengambilan sebanyak-banyaknya.

Balas HANYA JSON (tanpa teks lain):
{{"analysis": "...", "moments": [{{"start": 12.4, "end": 48.9, "title": "...", "hook": "...", "score": 9, "reason": "...", "trend": "...", "audience": "...", "bgm_mood": "comedy", "content_type": "podcast", "topic_tag": "", "loop": false, "loop_note": "", "layout": "single", "layout_events": []}}]}}"""


def _today() -> str:
    """Tanggal hari ini utk kesadaran zaman otak (dengan tahun)."""
    d = date.today()
    return f"{d.day} {['Januari','Februari','Maret','April','Mei','Juni','Juli','Agustus','September','Oktober','November','Desember'][d.month - 1]} {d.year}"


def _frames_note(frames, interval):
    if not frames:
        return "Tidak ada cuplikan frame — analisis hanya dari transkrip."
    n = len(frames)
    half = n // 2
    contoh = ", ".join(f"frame {i} = detik {i * interval:.1f}" for i in (0, half, n - 1))
    sparse = (interval or 0) >= 30.0
    padat = (
        f"Frame diambil SETIAP ±{interval:.0f} detik dari AWAL sampai AKHIR video "
        f"(contoh: {contoh}) — ini PANORAMA KESELURUHAN, bukan detail per momen. "
        f"Gunakan untuk: alur adengan/topik, siapa 'pemain utama', gaya visual, "
        f"dan PERKIRAAN kualitas visual suatu rentang (cari frame TERDEKAT dari "
        f"rentang kandidat). Jangan klaim detail ekspresi dari frame jarang."
        if sparse else
        f"Frame diambil SETIAP ±{interval:.0f} detik — cukup rapat utk menilai "
        f"ekspresi/reaksi/aksi per momen. Transkrip tetap sumber timestamp utama."
    )
    return (
        f"Dikirim juga {n} cuplikan FRAME GAMBAR dalam URUTAN WAKTU yang sama. "
        f"{padat} Frame menilai kualitas visual; transkrip tetap sumber timestamp utama."
    )


def _kids_note(is_kids: bool) -> str:
    if not is_kids:
        return ""
    return ("\n- MODE ANAK (deteksi otomatis): ini video anak-anak. Pilih momen lucu, "
            "imut, atau edukatif yang ramah keluarga; framing hangat & positif; "
            "hook yang bikin penasaran secara manis. JANGAN framing dramatis/"
            "klikbait gaya orang dewasa.\n")


def _build_prompt(transcript: dict, duration: float, frames, frame_interval, meta=None) -> str:
    """Bangun prompt v3: konteks (judul/channel/mode-anak) + proses 3 langkah.
    Dipisah jadi fungsi supaya bisa diuji tanpa API."""
    meta = meta or {}
    lines = "\n".join(
        f"[{l['start']:.1f}-{l['end']:.1f}]" + (f" {l['speaker']}:" if l.get("speaker") else "") + f" {l['text']}"
        for l in transcript["lines"]
    )
    return PROMPT.format(
        today=_today(),
        transcript=lines,
        title=(meta.get("title") or "—")[:200],
        uploader=(meta.get("uploader") or "—")[:120],
        kids_note=_kids_note(bool(meta.get("is_kids"))),
        frames_note=_frames_note(frames, frame_interval or 0),
        duration=round(duration),
        language=transcript["language"],
        max_clips=config.MAX_CLIPS,
        min_clip=int(config.MIN_CLIP_SEC),
        max_clip=int(config.MAX_CLIP_SEC),
    )


# ---------------- memori kesehatan model (PERMANEN, lintas run) ----------------
# Penguatan owner: masalah 'rantai model buang waktu' tidak boleh terulang
# "sepanjang masa". Model yang terbukti bermasalah dicatat di file —
# lintas run, lintas restart — sehingga TIDAK PERNAH lagi membuang
# percobaan ke model yang sama:
#   - model dimatikan Google (404) -> blacklist SELAMANYA
#   - kuota 0 struktural (limit:0 free tier) -> blacklist 7 hari (cek ulang mingguan)
#   - kuota harian habis (429 biasa) -> blacklist 24 jam (reset tiap hari)
# Kalau SEMUA model ter-blacklist (mis. ganti API key baru) -> blacklist
# diabaikan supaya tidak dead-lock (dicoba semua seperti biasa).

_HEALTH_FILE = config.MODELS_DIR / "model_health.json"


def _load_health() -> dict:
    try:
        return json.loads(_HEALTH_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_health(d: dict):
    try:
        _HEALTH_FILE.parent.mkdir(parents=True, exist_ok=True)
        now = time.time()
        # pruning: buang catatan kedaluwarsa saat menyimpan
        d = {m: v for m, v in d.items()
             if v.get("until") is None or v.get("until", 0) > now}
        _HEALTH_FILE.write_text(json.dumps(d, indent=1), encoding="utf-8")
    except Exception:
        pass


def _remember_model_failure(model: str, e):
    """Catat model bermasalah secara PERMANEN — dipakai semua run berikutnya."""
    s = str(e)
    now = time.time()
    if "no longer available" in s.lower() or "404" in s or "NOT_FOUND" in s:
        until, why = None, "model dimatikan Google (404) — selamanya"
    elif re.search(r"(quotaValue|limit)['\"]?\s*[:=]\s*['\"]?0\b", s):
        until = now + 7 * 86400
        why = "kuota 0 struktural (free tier) — cek ulang mingguan"
    else:
        until = now + 86400
        why = "kuota habis (reset harian) — cek ulang besok"
    d = _load_health()
    d[model] = {"until": until, "why": why, "at": now}
    _save_health(d)
    print(f"[brain] model '{model}' dicatat bermasalah: {why}", flush=True)


def _blacklisted_models() -> set:
    now = time.time()
    return {m for m, v in _load_health().items()
            if v.get("until") is None or v.get("until", 0) > now}


def _fallback_models() -> list:
    """Daftar model cadangan dari .env (GEMINI_FALLBACK_MODELS, dipisah koma),
    urutan dipertahankan, model utama & duplikat dibuang."""
    raw = config.GEMINI_FALLBACK_MODELS or ""
    seen = {config.GEMINI_MODEL}
    out = []
    for m in raw.split(","):
        m = m.strip()
        if m and m not in seen:
            out.append(m)
            seen.add(m)
    return out


def _model_attempts() -> list:
    """Urutan MODEL DISTINCT yang akan dicoba: utama lalu tiap cadangan
    (dalam urutan .env) — DIKURANGI model yang tercatat bermasalah di
    memori kesehatan permanen (model mati/kuota-0 tak pernah dipanggil
    lagi lintas run). Kalau SEMUA ter-blacklist (API key baru dsb) ->
    blacklist diabaikan supaya tidak dead-lock."""
    models = [config.GEMINI_MODEL] + _fallback_models()
    bad = _blacklisted_models()
    ok = [m for m in models if m not in bad]
    return ok if ok else models


def _is_quota_error(e) -> bool:
    """429 / RESOURCE_EXHAUSTED / kuota habis — PERMANEN untuk sesi ini
    (limit:0 tidak akan berubah dalam hitungan detik). Mengulang model
    YANG SAMA sia-sia -> harus lompat ke model lain SEGERA, tanpa jeda."""
    s = str(e)
    return "429" in s or "RESOURCE_EXHAUSTED" in s or "quota" in s.lower()


def _is_dead_model_error(e) -> bool:
    """404 / model dimatikan platform (mis. 'no longer available for new
    users') — PERMANEN selamanya, bukan cuma sesi ini. Sama seperti kuota:
    lompat segera, tanpa jeda."""
    s = str(e)
    return "404" in s or "NOT_FOUND" in s or "no longer available" in s.lower()


def _generate_with_fallback(client, types, parts):
    """
    Coba tiap model (utama lalu cadangan, GEMINI_FALLBACK_MODELS) satu per
    satu. Keputusan ulang/lompat PER JENIS ERROR:
    - kuota habis (429) / model dimatikan (404): PERMANEN -> lompat ke model
      berikutnya SEGERA, tanpa jeda, tanpa mengulang model yang sama
      (mengulang dijamin gagal lagi -> cuma buang waktu).
    - error sementara (503 sibuk, network, timeout, dll): layak diulang ->
      model utama diulang sampai GEMINI_PRIMARY_RETRIES kali dengan jeda
      GEMINI_RETRY_DELAY_SEC (beri waktu server pulih), cadangan sekali.
    Kalau semua model gagal, lempar error dengan ringkasan semua percobaan.
    """
    models = _model_attempts()
    errors = []
    total_tried = 0
    for mi, model in enumerate(models):
        max_tries = max(1, config.GEMINI_PRIMARY_RETRIES) if mi == 0 else 1
        attempt = 0
        while attempt < max_tries:
            attempt += 1
            total_tried += 1
            try:
                resp = client.models.generate_content(
                    model=model,
                    contents=parts,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        temperature=0.4,
                    ),
                )
                if total_tried > 1:
                    print(f"[brain] berhasil pakai model '{model}' "
                          f"(percobaan #{total_tried})", flush=True)
                return resp
            except Exception as e:
                errors.append(f"{model} (percobaan {attempt}): {e}")
                permanent = _is_quota_error(e) or _is_dead_model_error(e)
                if permanent:
                    _remember_model_failure(model, e)  # catat PERMANEN — lintas run
                reason = "PERMANEN, lompat segera" if permanent else "sementara"
                print(f"[brain] model '{model}' gagal [{reason}]: {e}", flush=True)
                is_last_model = mi == len(models) - 1
                if permanent:
                    break  # jangan ulangi model yang sama -> lompat ke model berikutnya
                if attempt < max_tries:
                    time.sleep(config.GEMINI_RETRY_DELAY_SEC)  # error sementara -> beri waktu pulih
                elif not is_last_model:
                    time.sleep(config.GEMINI_RETRY_DELAY_SEC)
                continue
    raise RuntimeError(
        "Semua model Gemini gagal (utama + cadangan). Rincian:\n" + "\n".join(errors)
    )


def find_moments(transcript: dict, duration: float,
                 frames_dir=None, frame_interval=None, meta=None) -> list:
    """
    Kirim transkrip + KONTEKS + frame ke Gemini -> daftar momen tervalidasi.
    MODE 1 OTAK (default): SATU panggilan — perilaku identik versi lama.
    MODE 5 OTAK (BRAIN_KEYS >= 2 kunci): KURATOR memilih momen, lalu
    VERIFIKATOR + PENULIS + DIREKTUR jalan PARALEL di kunci sendiri —
    tiap otak fokus SATU tugas (atensi tak terbagi), kegagalan satu otak
    hanya membatalkan polesan tugas itu (kurasi dasar tetap utuh).
    meta: {"title","uploader","is_kids"} dari pipeline (downloader.get_info).
    Model utama dicoba GEMINI_PRIMARY_RETRIES kali; kalau tetap gagal, turun ke
    daftar model cadangan (GEMINI_FALLBACK_MODELS) satu per satu.
    """
    if not (config.GEMINI_API_KEY or config.BRAIN_KEYS):
        raise RuntimeError("GEMINI_API_KEY / BRAIN_KEYS belum diisi di file .env")

    frames = []
    if frames_dir and frame_interval:
        from pathlib import Path
        frames = sorted(Path(frames_dir).glob("f_*.jpg"))[: config.BRAIN_MAX_FRAMES]

    prompt = _build_prompt(transcript, duration, frames, frame_interval, meta)
    moments = _extract_moments(_ask_role("kurator", prompt, frames))
    if moments and _multi_mode():
        moments = _specialist_pass(moments, transcript, duration, frames,
                                   frame_interval)
    return _validate(moments, transcript["words"], duration,
                     lines=transcript.get("lines"))


def _extract_moments(raw) -> list:
    """v3: {"analysis": "...", "moments": [...]} (proses berpikir terlatih).
    Format lama (array polos) tetap diterima. Jawaman aneh -> list kosong."""
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        m = raw.get("moments", [])
        return m if isinstance(m, list) else []
    return []


def _snap(t: float, words: list, mode: str, lines: list = None, tol: float = 2.0) -> float:
    """Geser timestamp ke batas kata terdekat (awal kata utk start, akhir kata
    utk end). Jalur caption (words kosong): pakai batas BARIS/kalimat —
    potongan TIDAK BOLEH nyangkal di tengah kalimat atau memotong pay-off.
    tol kecil (klip loop) = rapikan noise float saja, JANGAN geser potongan
    kata-presisi yang sudah dipilih otak."""
    if words:
        cands = [w["start"] for w in words] if mode == "start" else [w["end"] for w in words]
    elif lines:
        cands = [l["start"] for l in lines] if mode == "start" else [l["end"] for l in lines]
    else:
        return t
    best = min(cands, key=lambda c: abs(c - t))
    return best if abs(best - t) <= tol else t


def _validate(moments: list, words: list, duration: float, lines: list = None) -> list:
    out = []
    for m in moments:
        try:
            s = float(m["start"])
            e = float(m["end"])
        except (KeyError, TypeError, ValueError):
            continue
        is_loop = bool(m.get("loop", False))
        if float(m.get("score") or 0) < config.MIN_CLIP_SCORE:
            continue  # kurasi: "berdaging tapi datar" tak pernah jadi klip
        # klip loop: snap toleransi ketat (0.8s) — timestamp kata-presisi dari
        # otak DIPERCAYA; snap hanya merapikan noise, bukan menggeser potongan
        tol = 0.8 if is_loop else 2.0
        s = max(0.0, _snap(s, words, "start", lines, tol))
        e = min(duration, _snap(e, words, "end", lines, tol))
        if e - s < config.MIN_CLIP_SEC * 0.6:
            continue  # terlalu pendek setelah snap -> buang
        if e - s > config.MAX_CLIP_SEC:
            e = s + config.MAX_CLIP_SEC
        if out and s < out[-1]["end"] - 1.0:
            continue  # tumpang tindih -> buang
        out.append({
            "start": round(s, 2),
            "end": round(e, 2),
            "title": str(m.get("title", ""))[:80] or "Klip",
            "hook": str(m.get("hook", ""))[:120],
            "score": m.get("score", 0),
            "reason": str(m.get("reason", ""))[:200],
            "trend": str(m.get("trend", ""))[:120],
            "audience": str(m.get("audience", ""))[:120],
            "bgm_mood": str(m.get("bgm_mood", ""))[:20],
            "content_type": str(m.get("content_type", "")).lower()[:16],
            "topic_tag": str(m.get("topic_tag", "")).lower()[:24],
            "loop": is_loop,
            "loop_note": str(m.get("loop_note", ""))[:200],
            "layout": ("duo" if str(m.get("layout", "single")).lower() == "duo"
                       else "single"),
            "layout_events": _layout_events(m.get("layout_events"), e - s),
        })
    out.sort(key=lambda m: -float(m.get("score") or 0))
    return out[: config.MAX_CLIPS]


def _layout_events(raw, dur: float) -> list:
    """Validasi keras layout_events dari otak: hanya list dict dengan t di
    DALAM klip dan layout sah; maksimal 6 titik perubahan; urut."""
    out = []
    for ev in (raw or []):
        if not isinstance(ev, dict):
            continue
        try:
            t = float(ev.get("t", ev.get("time")))
        except (TypeError, ValueError):
            continue
        l = str(ev.get("layout", "")).lower()
        if 0.05 < t < dur - 0.05 and l in ("single", "duo"):
            out.append({"t": round(t, 2), "layout": l})
    out.sort(key=lambda x: x["t"])
    return out[:6]


# ================= 5 OTAK SPESIALIS: ruang kerja terpisah =================
ROLES = ("kurator", "verifikator", "penulis", "direktur", "analis")
_key_health = {}   # sesi: kunci kuota-habis -> digantikan tetangga SEGERA


def _brain_keys() -> list:
    """Kolam kunci: BRAIN_KEYS (khusus otak) atau [GEMINI_API_KEY] (legacy)."""
    if config.BRAIN_KEYS:
        return list(config.BRAIN_KEYS)
    return [config.GEMINI_API_KEY] if config.GEMINI_API_KEY else []


def _role_key(role: str, offset: int = 0) -> str:
    """Kunci milik otak ini (round-robin per tugas); kunci sakit digantikan
    tetangga terdekat (offset). Semua sakit = coba kunci asal (health basi)."""
    keys = _brain_keys()
    if not keys:
        raise RuntimeError("GEMINI_API_KEY / BRAIN_KEYS belum diisi di .env")
    base = ROLES.index(role)
    idx = (base + offset) % len(keys)
    if offset == 0:
        # kunci milik tugas ini SAKIT (kuota habis) -> tetangga terdekat
        # yang sehat ambil alih SEGERA; semua sakit = kunci asal (health basi)
        for off in range(len(keys)):
            k = keys[(base + off) % len(keys)]
            if not _key_health.get(k):
                return k
    return keys[idx]


def _multi_mode() -> bool:
    """auto: aktif bila >= 2 kunci; off: paksa 1-otak; multi: paksa aktif."""
    if config.BRAIN_MODE == "off":
        return False
    if config.BRAIN_MODE == "multi":
        return len(_brain_keys()) >= 1
    return len(_brain_keys()) >= 2


def _ask_role(role: str, prompt: str, frames=None):
    """Satu panggilan OTAK SPESIALIS: kunci sendiri (round-robin), fallback
    model tetap berlaku (model tertinggi -> turun level, mekanisme lama),
    kunci kuota-habis ditandai lalu digantikan tetangga SEGERA."""
    from google import genai
    from google.genai import types
    keys = _brain_keys()
    if not keys:
        raise RuntimeError("GEMINI_API_KEY / BRAIN_KEYS belum diisi di .env")
    parts = [types.Part.from_text(text=prompt)]
    for f in (frames or []):
        parts.append(types.Part.from_bytes(
            data=f.read_bytes(), mime_type="image/jpeg"))
    errors = []
    for off in range(len(keys)):
        key = _role_key(role, off)
        try:
            client = genai.Client(api_key=key)
            resp = _generate_with_fallback(client, types, parts)
            return json.loads(resp.text)
        except Exception as e:
            errors.append(f"{role}/kunci#{off + 1}: {e}")
            if _is_quota_error(e):
                _key_health[key] = True   # kuota habis -> otak lain ambil alih
    raise RuntimeError("; ".join(errors)[:600])


def _transcript_text(transcript: dict, max_chars=24000) -> str:
    """Transkrip ringkas BERTIMESTAMP utk otak teks (verifikator/penulis)."""
    lines = transcript.get("lines") or []
    if lines:
        segs = [f"[{l['start']:.1f}-{l['end']:.1f}] {l.get('text', '')}"
                for l in lines]
    else:
        segs = [f"[{w['start']:.1f}-{w['end']:.1f}] {w.get('text', '')}"
                for w in transcript.get("words", [])]
    return "\n".join(segs)[:max_chars]


_V_PROMPT = """Kamu EDITOR EKSEKUTIF VERIFIKATOR — satu-satunya tugas: menilai ulang
kandidat klip dengan standar TERTINGGI. Untuk TIAP kandidat, BACA teks
rentangnya dengan teliti di transkrip, lalu tanya:
1. "Kalau penonton acak melihat detik 1-3 klip ini di beranda, apakah dia
   BERHENTI scroll?"
2. Arc mini utuh: hook menarik -> isi menaikkan tensi/emosi/nilai -> pay-off
   memuaskan TEPAT di akhir?
3. Klip "berdaging tapi datar" (informasi ada tapi tak ada tensi/kejutan/
   emosi) = keep false — TOLAK tanpa ragu.
4. start/end harus TEPAT di batas kata/kalimat transkrip — kalau kurang tepat
   berikan start_fix/end_fix (detik, HARUS ada di transkrip); kalau sudah
   tepat isi 0.
5. hook_improved: versi hook yang lebih tajam dalam 1 kalimat pendek; kalau
   sudah bagus, salin apa adanya.
Bahasa keluaran WAJIB sama dengan bahasa transkrip. Balas HANYA JSON:
{{"verdicts": [{{"i": 0, "keep": true, "score": 8, "start_fix": 0, "end_fix": 0, "hook_improved": "..."}}]}}

TRANSKRIP (detik absolut):
{tr}

KANDIDAT:
{cand}"""


_W_PROMPT = """Kamu PENULIS JUDUL & HOOK profesional short-form. Untuk TIAP kandidat:
1. "title": tulis ulang maks 60 karakter — memancing wajib-tonton TANPA
   membocorkan pay-off, TANPA ALL-CAPS berlebihan, TANPA clickbait bohong.
   (judul ini juga jadi teks thumbnail)
2. "hook": satu kalimat pembuka memukul (maks 12 kata) — dipasang sebagai
   overlay teks besar di 2-3 detik pertama klip.
Jangan ubah fakta/makna. Bahasa keluaran WAJIB sama dengan bahasa transkrip.
Balas HANYA JSON: {{"rewrites": [{{"i": 0, "title": "...", "hook": "..."}}]}}

TRANSKRIP:
{tr}

KANDIDAT:
{cand}"""


_D_PROMPT = """Kamu DIREKTUR VISUAL. Frame dikirim SETIAP ±{iv:.1f} detik dari awal
video (frame i ≈ detik i×interval) dalam urutan waktu; rentang kandidat
dalam detik absolut video. Untuk TIAP kandidat:
1. "layout": "duo" HANYA kalau frame pada rentangnya benar-benar terbelah
   dua zona ATAS-BAWAH (wajah/pembicara di atas + gameplay/demo/presentasi
   di bawah) sehingga subtitle satu tempat menutupi salah satu zona; ragu =
   "single".
2. "layout_events": kalau terbelah hanya sebagian rentang:
   [{{"t": <detik RELATIF dari start klip>, "layout": "single"|"duo"}}]; utuh = [].
3. "topic_tag": satu topik berbahasa transkrip (finansial, gaming, cinta,
   bisnis, dst) — dipakai memilih emoji thumbnail.
4. "bgm_mood": satu dari: comedy, upbeat, epic, tension, mystery, emotional,
   chill, action.
Balas HANYA JSON: {{"directions": [{{"i": 0, "layout": "single", "layout_events": [], "topic_tag": "...", "bgm_mood": "chill"}}]}}

KANDIDAT:
{cand}"""


def _safe_result(fut):
    """Hasil masa depan -> dict; kegagalan otak apa pun -> {} (degradasi)."""
    try:
        r = fut.result()
        return r if isinstance(r, dict) else {}
    except Exception:
        return {}


def _specialist_pass(moments: list, transcript: dict, duration: float,
                     frames, frame_interval) -> list:
    """TIGA OTAK SPESIALIS jalan PARALEL di kunci sendiri:
    - VERIFIKATOR: nilai ulang tiap kandidat (drop yang datar, perbaiki
      timestamp & hook) — gerbang mutu kedua setelah kurator
    - PENULIS: poles judul & hook (menjadi teks thumbnail + overlay)
    - DIREKTUR: layout duo/split-layer + topic_tag + mood BGM (frame)
    Semua kegagalan otak hanya membatalkan polesan TUGAS ITU — kurasi
    kurator tetap utuh, pipeline TIDAK PERNAH gagal karena spesialis."""
    from concurrent.futures import ThreadPoolExecutor
    tr_text = _transcript_text(transcript)
    cand = json.dumps([{"i": i, "start": m.get("start"), "end": m.get("end"),
                        "title": m.get("title", ""), "hook": m.get("hook", ""),
                        "score": m.get("score")}
                       for i, m in enumerate(moments)], ensure_ascii=False)
    with ThreadPoolExecutor(max_workers=3) as ex:
        fv = ex.submit(_ask_role, "verifikator",
                       _V_PROMPT.format(tr=tr_text, cand=cand))
        fw = ex.submit(_ask_role, "penulis",
                       _W_PROMPT.format(tr=tr_text, cand=cand))
        fd = ex.submit(_ask_role, "direktur",
                       _D_PROMPT.format(iv=frame_interval or 0.0, cand=cand),
                       frames)
        verdicts = _safe_result(fv).get("verdicts") or []
        rewrites = _safe_result(fw).get("rewrites") or []
        directions = _safe_result(fd).get("directions") or []

    def _idx(v):
        try:
            i = int(v.get("i"))
            return i if 0 <= i < len(moments) else None
        except (TypeError, ValueError):
            return None

    dropped = set()
    for v in verdicts:
        i = _idx(v)
        if i is None:
            continue
        if v.get("keep") is False:
            dropped.add(i)
        else:
            if v.get("score") is not None:
                moments[i]["score"] = v.get("score")
            if v.get("hook_improved"):
                moments[i]["hook"] = str(v["hook_improved"])[:120]
            for fx, fld in (("start_fix", "start"), ("end_fix", "end")):
                try:
                    t = float(v.get(fx) or 0)
                    if 0 < t < duration:
                        moments[i][fld] = t
                except (TypeError, ValueError):
                    pass
    for r in rewrites:
        i = _idx(r)
        if i is not None:
            if r.get("title"):
                moments[i]["title"] = str(r["title"])[:80]
            if r.get("hook"):
                moments[i]["hook"] = str(r["hook"])[:120]
    for d in directions:
        i = _idx(d)
        if i is not None:
            moments[i]["layout"] = str(d.get("layout", "single")).lower()[:8]
            moments[i]["layout_events"] = d.get("layout_events") or []
            if d.get("topic_tag"):
                moments[i]["topic_tag"] = str(d["topic_tag"]).lower()[:24]
            if d.get("bgm_mood"):
                moments[i]["bgm_mood"] = str(d["bgm_mood"]).lower()[:20]
    return [m for i, m in enumerate(moments) if i not in dropped]
