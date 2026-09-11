"""
Transkripsi hemat CPU: faster-whisper dengan timestamp PER KATA (word-level).
Timestamp per kata = kunci potongan yang presisi & subtitle karaoke.
Model & compute type diatur di config (default: small + int8).
"""
import time

from . import config

_model = None


def _get_model():
    global _model
    if _model is None:
        from faster_whisper import WhisperModel
        _model = WhisperModel(config.WHISPER_MODEL, device="cpu", compute_type=config.WHISPER_COMPUTE)
    return _model


def transcribe(audio_path, expected_duration=None, on_progress=None) -> dict:
    """-> {"language": "id", "lines": [{start,end,text}], "words": [{start,end,text}]}"""
    model = _get_model()
    segments, info = model.transcribe(
        str(audio_path),
        word_timestamps=True,
        vad_filter=True,                        # buang keheningan -> kurangi halusinasi
        condition_on_previous_text=False,       # anti typo-berulang/drift saat bicara cepat
        beam_size=config.WHISPER_BEAM,           # beam 5 = jauh lebih akurat dari greedy
        vad_parameters={"min_silence_duration_ms": 500},
    )
    lines, words = [], []
    last_cb = 0.0
    for seg in segments:  # generator — iterasi sekali saja biar hemat memori
        if on_progress and expected_duration and expected_duration > 0:
            now = time.time()
            if now - last_cb >= 2.0:  # throttled: update paling tiap 2 dtk
                last_cb = now
                on_progress(min(0.98, max(0.0, seg.end / expected_duration)))
        text = seg.text.strip()
        if not text:
            continue
        lines.append({"start": seg.start, "end": seg.end, "text": text})
        for w in (seg.words or []):
            t = w.word.strip()
            if t:
                words.append({"start": w.start, "end": w.end, "text": t})
    return {"language": info.language, "lines": lines, "words": words}
