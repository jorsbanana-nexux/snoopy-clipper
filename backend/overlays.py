"""Overlay PNG untuk klip: WATERMARK ala UI lama Snoopy (SNOOPY kuning +
CLIPPER putih, tebal, semi-transparan, pojok KIRI-ATAS) dan teks HOOK besar
2-3 detik pertama. PNG alpha dibuat via Pillow (fallback font lintas-OS),
di-cache per resolusi. Semua kegagalan ditelan oleh pemanggil — overlay
TIDAK PERNAH boleh mematikan render."""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

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


def make_hook(hook_text, tw, th, path):
    """PNG teks HOOK besar (tampil 2-3 detik pertama): putih tebal +
    outline hitam tebal, max 2 baris, lebar kanvas = lebar klip (posisi
    center diatur overlay filter). Kembalikan path atau None bila kosong."""
    text = " ".join((hook_text or "").split()[:6])
    if not text:
        return None
    size = max(22, int(th * 0.052))
    f = _font(size)
    probe = ImageDraw.Draw(Image.new("RGBA", (8, 8)))
    lines = _wrap(probe, text, f, tw * 0.84)
    asc, desc = f.getmetrics()
    line_h = int((asc + desc) * 1.15)
    stroke = max(3, size // 11)
    H = line_h * len(lines) + stroke * 2 + 6
    im = Image.new("RGBA", (tw, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    y = 3
    for ln in lines:
        w = d.textlength(ln, font=f)
        d.text(((tw - w) / 2, y), ln, font=f, fill=(255, 255, 255, 247),
               stroke_width=stroke, stroke_fill=(0, 0, 0, 255))
        y += line_h
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    im.save(p)
    return p
