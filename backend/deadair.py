"""Dead-air removal: jeda napas panjang di TENGAH klip dipotong (jump cut)
memakai timestamp kata Whisper — podcast jadi rapat, tak ngelantur.
AMAN BY DESIGN:
- hanya gap INTERIOR (batas klip tak tersentuh), pad 0.15s menjaga intonasi
- tiap sisi potongan wajib >= 1.2s; klip < 4s tak diproses
- total buangan dibatasi 40% (lebih dari itu = batal, render normal)
- hasil tunggal-segmen = PERILAKU LAMA IDENTIK (dikunci test)
- DEADAIR=0 di .env = rollback instan"""
from . import config


def segments(words, clip_start: float, clip_end: float):
    dur = clip_end - clip_start
    if (not config.DEADAIR or dur < 4.0 or not words):
        return [(clip_start, clip_end)]
    gap = config.DEADAIR_GAP
    pad = 0.15
    min_seg = 1.2
    ws = sorted((w for w in words
                 if w["end"] > clip_start + 0.05 and w["start"] < clip_end - 0.05),
                key=lambda w: w["start"])
    cuts = []
    for a, b in zip(ws, ws[1:]):
        c0 = a["end"] + pad
        c1 = b["start"] - pad
        if b["start"] - a["end"] >= gap and c1 - c0 >= 0.08:
            cuts.append((round(c0, 3), round(c1, 3)))
    keep, cur = [], clip_start
    for (c0, c1) in cuts:  # buang cut yang bikin segmen kecil di salah satu sisi
        if c0 - cur >= min_seg and clip_end - c1 >= min_seg:
            keep.append((c0, c1))
            cur = c1
    segs, cur = [], clip_start
    for (c0, c1) in keep:
        segs.append((cur, c0))
        cur = c1
    segs.append((cur, clip_end))
    if len(segs) < 2 or sum(e - s for s, e in segs) < dur * 0.6:
        return [(clip_start, clip_end)]
    return segs


def _t(kf):
    if isinstance(kf, dict):
        for k in ("t", "time", "ts"):
            if k in kf:
                return kf[k]
        return None
    if isinstance(kf, (list, tuple)) and len(kf):
        return kf[0]
    return None


def rebase_keyframes(keyframes, s: float, e: float):
    """Geser keyframe crop ke timeline sub-segment (t-s). Tak ada keyframe
    dalam rentang -> pakai yang terdekat di-clamp ke 0 (crop tetap pintar)."""
    if not keyframes:
        return keyframes
    out = []
    for kf in keyframes:
        t = _t(kf)
        if t is None:
            out.append(kf)
        elif s - 0.05 <= t <= e + 0.05:
            if isinstance(kf, dict):
                nk = dict(kf)
                for k in ("t", "time", "ts"):
                    if k in nk:
                        nk[k] = round(nk[k] - s, 3)
                out.append(nk)
            else:
                out.append((round(t - s, 3),) + tuple(kf[1:]))
    if not out:
        near = min(keyframes, key=lambda k: abs((_t(k) if _t(k) is not None else 0) - s))
        nt = _t(near)
        if isinstance(near, dict):
            nk = dict(near)
            for k in ("t", "time", "ts"):
                if k in nk:
                    nk[k] = 0.0
            out.append(nk)
        else:
            out.append((0.0,) + tuple(near[1:]))
    return out
