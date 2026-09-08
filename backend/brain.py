"""
OTAK SNOOPY v4 — ELITE + TERLATIH + MULTIMODAL: berpikir KONTEKS DULU, baru memilih.
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
import time

from . import config

PROMPT = """Kamu adalah OTAK SNOOPY v4 — editor video viral LEGENDARIS yang TERLATIH: klip-klipmu menghasilkan ratusan juta views di semua platform (YouTube Shorts, TikTok, Reels) dan SEMUA jenis konten: podcast, wawancara, gaming, storytime, vlog, berita, edukasi, sampai video anak. Kamu hafal di luar kepala psikologi penonton pendek: retensi 2 detik pertama, curiosity gap, trigger share/save/komentar, dan pola klip yang bikin orang berhenti scroll lalu menonton sampai habis dan menonton ulang.

KONTEKS VIDEO:
- Judul: {title}
- Channel: {uploader}
- Durasi: {duration} detik. Bahasa: {language}.
{kids_note}
{frames_note}

Transkrip video (format [detik_awal-detik_akhir] teks):
{transcript}

PROSES TERLATIH — kerjakan 3 langkah berurutan, tulis hasilnya ringkas di kolom "analysis" (maks 5 kalimat):
LANGKAH 1 — PAHAMI DULU (sebelum memilih): dari judul + channel + transkrip (+frame kalau ada), pahami: siapa saja yang terlibat, topik inti, jenis konten, dan DI MANA "DAGING"-nya. Contoh: judulnya tentang pencurian mobil -> cari di transkrip bagian di mana kisahnya DIBERITAHUKAN dengan detail (siapa, di mana, kapan, berapa rugi, reaksi emosinya) — dagingnya di situ, bukan di basa-basi pembuka.
LANGKAH 2 — NILAI SEBAGAI PENONTON ACAK yang tidak tahu apa-apa soal video ini: bagian mana yang bikin kaget / "hah, serius?" / kagum / emosi / tertawa / penasaran sampai selesai? Bagian yang akan ditonton ulang dan dikomentari penonton — itulah kandidatnya.
LANGKAH 3 — PILIH momen terbaik dengan ATURAN KETAT di bawah. Kerjakan dengan standar tertinggi: setiap klip yang kamu pilih harus layak diunggah sendiri dan meraup views.

ATURAN KETAT momen:
1. Utuh dan berdaging: konteks awal yang LANGSUNG jelas bagi penonton baru -> membangun -> pay-off / klimaks / twist / punchline / kesimpulan kuat. JANGAN basa-basi, iklan, sapaan kosong, atau momen asal tanpa isi.
2. start TEPAT di kalimat pertama yang membuat penonton baru langsung paham konteksnya (contoh sempurna: "John, kenapa sih mobilmu bisa dicuri?" — pertanyaan + konteks dalam satu napas), end TEPAT setelah pay-off selesai. start & end HARUS timestamp yang benar-benar muncul di transkrip. Ini yang paling penting.
3. Durasi tiap potongan {min_clip}-{max_clip} detik. JUMLAH FLEKSIBEL — ikuti kualitas video, BUKAN kuota: pilih SEMUA momen yang benar-benar layak (score 7-10). Jangan paksa jumlah (video datar = sedikit saja), jangan buang momen layak, dan jangan tambah momen asal demi jumlah. Bisa jadi 3, bisa jadi 30 — yang penting setiap klip layak viral. Batas teknis {max_clips} hanyalah pengaman. Tidak boleh saling tumpang tindih.
4. Gunakan FRAME (kalau dikirim) untuk menilai kualitas visual: ekspresi kuat, reaksi, aksi, kejadian di layar. Momen kuat di teks TAPI lemah/monoton secara visual harus kalah dari momen yang kuat di keduanya.
5. Adaptif jenis konten: podcast/wawancara -> hot take, kisah pribadi, adu argumen, pengakuan mengejutkan; gaming -> clutch, rage, lucu tak terduga; berita/storytime -> bagian paling mengejutkan dengan detail paling spesifik; edukasi -> tip paling berguna dengan contoh nyata; vlog -> momen paling emosional/tak terduga.
6. Judul + hook harus memancing "wajib tonton" dalam 1-2 detik TANPA membocorkan pay-off. Semua teks dalam bahasa transkrip.
7. score 1-10 jujur (10 = wajib tonton). Hanya sertakan momen score 7 ke atas — di bawah itu buang; klip biasa-biasa saja = penonton scroll lewat = views mati.
8. Tes akhir untuk tiap kandidat seperti editor legendaris: "kalau klip ini diunggah, apakah orang SHARE / SAVE / komentar 'apasih'?" Kalau tidak ada yang akan, jangan pilih. Utamakan momen yang menonton sekali lalu menonton ulang (loop).

Balas HANYA JSON (tanpa teks lain):
{{"analysis": "...", "moments": [{{"start": 12.4, "end": 48.9, "title": "...", "hook": "...", "score": 9, "reason": "..."}}]}}"""


def _frames_note(frames, interval):
    if not frames:
        return "Tidak ada cuplikan frame — analisis hanya dari transkrip."
    n = len(frames)
    half = n // 2
    contoh = ", ".join(f"frame {i} = detik {i * interval:.1f}" for i in (0, half, n - 1))
    return (
        f"Dikirim juga {n} cuplikan FRAME GAMBAR dalam URUTAN WAKTU yang sama "
        f"(contoh: {contoh}). Gunakan frame untuk: memahami momen VISUAL "
        "(ekspresi, reaksi, aksi, kejadian di layar), pergantian adegan, "
        "dan siapa 'pemain utama' yang sedang dibahas/di-highlight. "
        "Transkrip tetap sumber timestamp utama; frame menilai kualitas visual."
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
        f"[{l['start']:.1f}-{l['end']:.1f}] {l['text']}" for l in transcript["lines"]
    )
    return PROMPT.format(
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
    """Urutan model yang akan dicoba: model utama diulang GEMINI_PRIMARY_RETRIES kali,
    lalu tiap model cadangan sekali (dalam urutan .env) sampai ada yang lolos."""
    retries = max(1, config.GEMINI_PRIMARY_RETRIES)
    attempts = [config.GEMINI_MODEL] * retries
    attempts += _fallback_models()
    return attempts


def _generate_with_fallback(client, types, parts):
    """
    Coba model utama sampai GEMINI_PRIMARY_RETRIES kali (jaga-jaga error
    transient seperti 503 high-demand), lalu turun ke model cadangan satu per
    satu (GEMINI_FALLBACK_MODELS) sampai ada yang berhasil. Kalau semua gagal,
    lempar error terakhir dengan ringkasan semua percobaan.
    """
    attempts = _model_attempts()
    errors = []
    for i, model in enumerate(attempts):
        try:
            resp = client.models.generate_content(
                model=model,
                contents=parts,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.4,
                ),
            )
            if i > 0:
                print(f"[brain] berhasil pakai model '{model}' "
                      f"(percobaan #{i + 1}/{len(attempts)})", flush=True)
            return resp
        except Exception as e:
            errors.append(f"{model}: {e}")
            print(f"[brain] model '{model}' gagal (percobaan #{i + 1}/{len(attempts)}): {e}",
                  flush=True)
            if i < len(attempts) - 1:
                time.sleep(config.GEMINI_RETRY_DELAY_SEC)
            continue
    raise RuntimeError(
        "Semua model Gemini gagal (utama + cadangan). Rincian:\n" + "\n".join(errors)
    )


def find_moments(transcript: dict, duration: float,
                 frames_dir=None, frame_interval=None, meta=None) -> list:
    """
    Kirim transkrip + KONTEKS (judul/channel/mode-anak) + frame (kalau ada)
    ke Gemini -> daftar momen tervalidasi. Tetap SATU panggilan LLM —
    proses 3-langkah terjadi di dalam prompt, nol langkah tambahan.
    meta: {"title","uploader","is_kids"} dari pipeline (downloader.get_info).
    Model utama dicoba GEMINI_PRIMARY_RETRIES kali; kalau tetap gagal, turun ke
    daftar model cadangan (GEMINI_FALLBACK_MODELS) satu per satu.
    """
    if not config.GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY belum diisi di file .env")
    from google import genai
    from google.genai import types

    frames = []
    if frames_dir and frame_interval:
        from pathlib import Path
        frames = sorted(Path(frames_dir).glob("f_*.jpg"))[: config.BRAIN_MAX_FRAMES]

    prompt = _build_prompt(transcript, duration, frames, frame_interval, meta)

    parts = [types.Part.from_text(text=prompt)]
    for f in frames:
        parts.append(types.Part.from_bytes(
            data=f.read_bytes(), mime_type="image/jpeg"
        ))

    client = genai.Client(api_key=config.GEMINI_API_KEY)
    resp = _generate_with_fallback(client, types, parts)
    raw = json.loads(resp.text)
    return _validate(_extract_moments(raw), transcript["words"], duration)


def _extract_moments(raw) -> list:
    """v3: {"analysis": "...", "moments": [...]} (proses berpikir terlatih).
    Format lama (array polos) tetap diterima. Jawaman aneh -> list kosong."""
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        m = raw.get("moments", [])
        return m if isinstance(m, list) else []
    return []


def _snap(t: float, words: list, mode: str) -> float:
    """Geser timestamp ke batas kata terdekat (awal kata utk start, akhir kata utk end)."""
    if not words:
        return t
    cands = [w["start"] for w in words] if mode == "start" else [w["end"] for w in words]
    best = min(cands, key=lambda c: abs(c - t))
    return best if abs(best - t) <= 2.0 else t


def _validate(moments: list, words: list, duration: float) -> list:
    out = []
    for m in moments:
        try:
            s = float(m["start"])
            e = float(m["end"])
        except (KeyError, TypeError, ValueError):
            continue
        s = max(0.0, _snap(s, words, "start"))
        e = min(duration, _snap(e, words, "end"))
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
        })
    out.sort(key=lambda m: -float(m.get("score") or 0))
    return out[: config.MAX_CLIPS]
