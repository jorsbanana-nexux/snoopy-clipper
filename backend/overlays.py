"""Overlay PNG untuk klip: WATERMARK ala UI lama Snoopy (SNOOPY kuning +
CLIPPER putih, tebal, semi-transparan, pojok KIRI-ATAS) dan teks HOOK besar
2-3 detik pertama. PNG alpha dibuat via Pillow (fallback font lintas-OS),
di-cache per resolusi. Semua kegagalan ditelan oleh pemanggil — overlay
TIDAK PERNAH boleh mematikan render."""
from pathlib import Path

import urllib.request

from PIL import Image, ImageDraw, ImageFilter, ImageFont

_ALPHA = 199  # ~78% — semi-transparan ("agar transparan")

_FONT_CANDS = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/segoeuib.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
)


def _font(size: int):
    for p in _FONT_CANDS:
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def make_watermark(tw, th, workdir):
    """PNG watermark 'SNOOPY CLIPPER' dua warna. Kanvas = ukuran teks;
    posisi kiri-atas diatur oleh overlay filter (main_w*0.035, main_h*0.025).
    Cache per resolusi (tw,th) — nyaris nol biaya per klip."""
    out = Path(workdir) / f"wm_{tw}x{th}.png"
    if out.exists():
        return out
    size = max(16, int(th * 0.026))
    f = _font(size)
    probe = ImageDraw.Draw(Image.new("RGBA", (8, 8)))
    w1 = probe.textlength("SNOOPY ", font=f)
    w2 = probe.textlength("CLIPPER", font=f)
    asc, desc = f.getmetrics()
    W = int(w1 + w2) + 8
    H = int(asc + desc) + 6
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    # tebal: stroke warna sama mempertebal bentuk
    d.text((4, 3), "SNOOPY ", font=f, fill=(255, 221, 0, _ALPHA),
           stroke_width=2, stroke_fill=(255, 221, 0, _ALPHA))
    d.text((4 + w1, 3), "CLIPPER", font=f, fill=(255, 255, 255, _ALPHA),
           stroke_width=2, stroke_fill=(255, 255, 255, _ALPHA))
    out.parent.mkdir(parents=True, exist_ok=True)
    im.save(out)
    return out


def _wrap(draw, text, f, max_w):
    lines, cur = [], ""
    for w in text.split():
        cand = (cur + " " + w).strip()
        if draw.textlength(cand, font=f) <= max_w or not cur:
            cur = cand
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines[:2]  # max 2 baris — hook pendek menengarkan


def _hook_font(size: int):
    """Milky Moringa Bold (pilihan owner 2026-09-12, unduh sekali via
    fontdisplay) -> fallback Anton (Google Fonts, OFL) -> font sistem.
    Cache permanen models/fonts/; TIDAK PERNAH raise."""
    try:
        from . import fontdisplay
        mf = fontdisplay.ensure()
        if mf:
            return ImageFont.truetype(mf, size)
    except Exception:
        pass
    try:
        from . import config
        p = config.MODELS_DIR / "fonts" / "anton.ttf"
        if not p.exists():
            p.parent.mkdir(parents=True, exist_ok=True)
            data = urllib.request.urlopen(
                "https://github.com/google/fonts/raw/main/ofl/anton/"
                "Anton-Regular.ttf", timeout=20).read()
            p.write_bytes(data)
        return ImageFont.truetype(p, size)
    except Exception:
        return None


# shadow gelap: (radius sbg fraksi LEBAR KLIP, alpha) — dari lapis terluar
# paling lembut ke terdalam. 5 lapis = "gelap radius jauh hampir menutupi
# layar, tapi batas wajar tidak terlalu hitam" — efek gradient lembut.
_HOOK_SHADOW = ((0.045, 55), (0.030, 80), (0.018, 115), (0.009, 160),
                (0.004, 210))


def _with_alpha(im, a: float):
    """Kalikan alpha channel dengan faktor 0..1 (utk frame fade)."""
    r, g, b, al = im.split()
    al = al.point(lambda v: int(v * a))
    return Image.merge("RGBA", (r, g, b, al))


def make_hook(hook_text, tw, th, path, dur=2.6):
    """APNG teks HOOK besar (tampil 2-3 detik pertama): putih BERSIH tebal
    (font Milky Moringa Bold, fallback Anton) TANPA outline hitam — hanya
    shadow gelap banyak-lapis radius
    jauh ala gradient (permintaan owner 2026-09-11). Animasi fade subtitle:
    lead-in transparan -> fade-in -> hold -> FADE-OUT + BLUR memudar."""
    text = " ".join((hook_text or "").split()[:6])
    if not text:
        return None
    size = max(22, int(th * 0.052))
    f = _hook_font(size) or _font(size)
    probe = ImageDraw.Draw(Image.new("RGBA", (8, 8)))
    lines = _wrap(probe, text, f, tw * 0.84)
    asc, desc = f.getmetrics()
    line_h = int((asc + desc) * 1.15)
    H = line_h * len(lines) + 6
    base = Image.new("RGBA", (tw, H), (0, 0, 0, 0))
    ys = [3 + i * line_h for i in range(len(lines))]
    # SHADOW gradient gelap: 5 lapis blur hitam, dari sangat lebar-halus
    # ke sempit-pekat — menutupi area luas TANPA outline hitam sama sekali
    for frac, alpha in _HOOK_SHADOW:
        sh = Image.new("RGBA", base.size, (0, 0, 0, 0))
        sd = ImageDraw.Draw(sh)
        for y, ln in zip(ys, lines):
            w = sd.textlength(ln, font=f)
            sd.text(((tw - w) / 2, y), ln, font=f, fill=(0, 0, 0, alpha))
        sh = sh.filter(ImageFilter.GaussianBlur(max(2, int(tw * frac))))
        base.alpha_composite(sh)
    # TEKS putih bersih tebal — no stroke, no outline hitam
    d = ImageDraw.Draw(base)
    for y, ln in zip(ys, lines):
        w = d.textlength(ln, font=f)
        d.text(((tw - w) / 2, y), ln, font=f, fill=(255, 255, 255, 247))
    # ANIMASI ala fade subtitle: 0.15s transparan (jeda masuk) -> fade-in
    # 0.28s -> hold -> fade-out 0.55s dgn blur bertambah sampai lenyap.
    lead, fin, fout = 0.15, 0.28, 0.55
    hold = max(0.0, dur - lead - fin - fout)
    frames, times = [], []
    blank = Image.new("RGBA", base.size, (0, 0, 0, 0))

    def _fr(src):
        fr = Image.new("RGBA", base.size, (0, 0, 0, 0))
        fr.alpha_composite(src)
        return fr

    frames.append(_fr(blank)); times.append(int(lead * 1000))
    for i in range(1, 6):  # fade-in halus 5 frame
        frames.append(_fr(_with_alpha(base, i / 5)))
        times.append(int(fin * 1000 / 5))
    if hold > 0:
        frames.append(_fr(base)); times.append(int(hold * 1000))
    for i in range(1, 13):  # fade-out + blur memudar 12 frame
        t = i / 12
        b = base.filter(ImageFilter.GaussianBlur(1 + t * 9))
        frames.append(_fr(_with_alpha(b, 1 - t)))
        times.append(int(fout * 1000 / 12))
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    frames[0].save(p, save_all=True, append_images=frames[1:],
                   duration=times, loop=1, disposal=2)
    return p
