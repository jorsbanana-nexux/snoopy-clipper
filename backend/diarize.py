"""
Diarization OPSIONAL (default MATI): label pembicara per kata & baris.

Desain buat PC low-spec + tidak pernah merusak pipeline:
- DIARIZE != "1"  -> tidak ada import, nol biaya (kembali apa adanya).
- Library/model/token tidak ada -> WARNING + kembali tanpa label
  (pipeline jalan 100% seperti sebelum modul ini).
- Mesin: pyannote speaker-diarization-3.1 (CPU) — model kecil (~90 MB),
  sekali unduh lalu tersimpan di HF cache (local-first).

Setup (sekali):
  1. Buat akun HuggingFace gratis -> Settings -> Access token (fine-grained, read).
  2. Buka https://huggingface.co/pyannote/speaker-diarization-3.1 dan
     https://huggingface.co/pyannote/segmentation-3.0 -> klik "Agree and access repository".
  3. pip install -r requirements-diarize.txt
  4. .env: DIARIZE=1  dan  DIARIZE_TOKEN=hf_xxx
"""
from . import config


def assign_speakers(transcript: dict, turns) -> dict:
    """Inti murni (testable tanpa pyannote).

    turns: iterable (start, end, speaker_label) hasil diarization.
    Kata  -> pembicara yang overlap-nya PALING BESAR.
    Baris -> pembicara mayoritas kata-katanya.
    Kalau cuma 1 pembicara terdeteksi -> label DIBUANG (transkrip kembali polos,
    prompt otak tetap ramping). Mutasi salinan, input tidak diubah.
    """
    turns = [(float(s), float(e), str(sp)) for s, e, sp in turns if float(e) > float(s)]
    if not turns:
        return transcript
    labels = {sp for _, _, sp in turns}
    if len(labels) < 2:
        return transcript  # monolog: label tidak menambah info

    def _pick(start, end):
        best, best_ov = None, 0.0
        for ts, te, sp in turns:
            ov = min(end, te) - max(start, ts)
            if ov > best_ov:
                best, best_ov = sp, ov
        return best

    out = dict(transcript)
    words = []
    for w in transcript.get("words", []):
        w2 = dict(w)
        sp = _pick(w["start"], w["end"])
        if sp:
            w2["speaker"] = sp
        words.append(w2)
    out["words"] = words

    lines = []
    for l in transcript.get("lines", []):
        l2 = dict(l)
        ws = [w for w in words if w["start"] >= l["start"] - 1e-6 and w["end"] <= l["end"] + 1e-6]
        if ws:
            votes = {}
            for w in ws:
                votes[w.get("speaker")] = votes.get(w.get("speaker"), 0) + 1
            top = max(votes.items(), key=lambda kv: kv[1])
            if top[0] and top[1] >= max(1, len(ws) // 2):
                l2["speaker"] = top[0]
        lines.append(l2)
    out["lines"] = lines
    return out


def maybe_diarize(transcript: dict, wav_path, on_progress=None) -> dict:
    """Hook pipeline: kembalikan transkrip + label pembicara kalau DIARIZE=1.
    Gagal apa pun -> transkrip asli dikembalikan utuh (tidak pernah raise)."""
    if not config.DIARIZE or not transcript.get("words"):
        return transcript
    try:
        from pyannote.audio import Pipeline  # lazy: tidak terpakai = tidak diimport

        if on_progress:
            on_progress(0.05, "Diarization: memuat model…")
        pipe = Pipeline.from_pretrained(
            config.DIARIZE_MODEL, use_auth_token=config.DIARIZE_TOKEN or None)
        if on_progress:
            on_progress(0.2, "Diarization: mengenali pembicara…")
        diar = pipe(str(wav_path))
        # itertracks(yield_label=True) -> (Segment, track_name, label)
        turns = [(t.start, t.end, spk) for t, _tr, spk in diar.itertracks(yield_label=True)]
        out = assign_speakers(transcript, turns)
        if on_progress:
            n = len({l.get("speaker") for l in out["lines"] if l.get("speaker")})
            on_progress(1.0, f"Diarization selesai: {n} pembicara" if n else "Diarization: monolog")
        return out
    except Exception as e:  # noqa: BLE001 — memang sengaja: fallback total
        import logging
        logging.getLogger(__name__).warning("Diarization dilewati (%s)", e)
        return transcript
