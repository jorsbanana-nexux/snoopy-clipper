"""
OTAK SNOOPY v2 — MULTIMODAL: kini bisa MELIHAT, bukan cuma membaca.
Kirim transkrip + cuplikan frame (gambar, urut waktu) ke Gemini ->
momen dipilih dari ISI + KUALITAS VISUAL (ekspresi, reaksi, aksi, pergantian adegan).
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

PROMPT = """Kamu adalah editor video profesional kelas dunia yang ahli menemukan momen paling "berdaging" dari video panjang untuk dijadikan konten pendek viral (YouTube Shorts / TikTok / Reels). Kerjamu dipakai di video apa pun: podcast, vlog, gaming, reaksi, edukasi, hingga video anak — platform dan topik tidak penting, kualitas momen yang penting.

Transkrip video (format [detik_awal-detik_akhir] teks):
{transcript}

{frames_note}

Durasi total: {duration} detik. Bahasa transkrip: {language}.

Pilih maksimal {max_clips} potongan TERBAIK dengan aturan ketat:
1. Setiap potongan HARUS momen utuh yang berdaging: konteks awal yang langsung jelas -> membangun -> pay-off / klimaks / twist / punchline / kesimpulan kuat. JANGAN pilih basa-basi, iklan, sapaan kosong, atau momen asal tanpa isi.
2. Gunakan FRAME untuk menilai kualitas visual momen: utamakan momen dengan ekspresi kuat, reaksi, aksi, atau kejadian visual yang menarik. Momen yang bagus di teks TAPI lemah/monoton secara visual harus kalah oleh momen yang kuat di keduanya.
3. Durasi tiap potongan antara {min_clip}-{max_clip} detik.
4. start & end HARUS timestamp yang benar-benar muncul di transkrip. start TEPAT di awal kalimat yang membuat konteks langsung dipahami penonton baru, end TEPAT setelah pay-off selesai — tidak terlalu awal (bingung), tidak terlalu akhir (bosen). Ini yang paling penting.
5. Beri hook (kalimat/ide pembuka yang bikin penasaran dalam 1-2 detik), judul singkat menarik, dan score 1-10 (10 = wajib tonton).
6. Potongan tidak boleh saling tumpang tindih.
7. Judul, hook, dan reason ditulis dalam bahasa transkrip.

Balas HANYA array JSON tanpa penjelasan lain:
[{{"start": 12.4, "end": 48.9, "title": "...", "hook": "...", "score": 9, "reason": "..."}}]"""


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
                 frames_dir=None, frame_interval=None) -> list:
    """
    Kirim transkrip (+ frame kalau ada) ke Gemini -> daftar momen tervalidasi.
    frames_dir: folder f_001.jpg, f_002.jpg, ... (frame ke-i = detik i*interval).
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

    lines = "\n".join(
        f"[{l['start']:.1f}-{l['end']:.1f}] {l['text']}" for l in transcript["lines"]
    )
    prompt = PROMPT.format(
        transcript=lines,
        frames_note=_frames_note(frames, frame_interval or 0),
        duration=round(duration),
        language=transcript["language"],
        max_clips=config.MAX_CLIPS,
        min_clip=int(config.MIN_CLIP_SEC),
        max_clip=int(config.MAX_CLIP_SEC),
    )

    parts = [types.Part.from_text(text=prompt)]
    for f in frames:
        parts.append(types.Part.from_bytes(
            data=f.read_bytes(), mime_type="image/jpeg"
        ))

    client = genai.Client(api_key=config.GEMINI_API_KEY)
    resp = _generate_with_fallback(client, types, parts)
    raw = json.loads(resp.text)
    moments = raw if isinstance(raw, list) else raw.get("moments", [])
    return _validate(moments, transcript["words"], duration)


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
