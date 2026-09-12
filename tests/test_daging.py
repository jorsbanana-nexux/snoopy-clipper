"""Daging klip: voice treatment (-14 LUFS), watermark dua warna, hook overlay,
dead-air jump-cut + concat + BGM pasca-concat. Kontrak: tanpa gap -> SATU PASS
normal (perilaku lama + daging); flag .env = rollback instan."""
import subprocess

from PIL import Image

from backend import config, cutter, deadair, overlays


def _mkvideo(path, dur=8.0, w=320, h=568):
    subprocess.run(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
         "-f", "lavfi", "-i", f"testsrc2=size={w}x{h}:rate=24:duration={dur}",
         "-f", "lavfi", "-i", f"sine=frequency=440:duration={dur}",
         "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
         "-c:a", "aac", str(path)], check=True)


def test_voice_chain():
    v = cutter._voice_chain()
    assert "loudnorm=I=-14" in v and "highpass=f=80" in v and "afftdn" in v
    old = config.VOICE_TREAT
    config.VOICE_TREAT = False
    assert cutter._voice_chain() == ""          # rollback: perilaku lama
    config.VOICE_TREAT = old


def test_watermark_dua_warna_transparan_dan_cache(tmp_path):
    p = overlays.make_watermark(720, 1280, tmp_path)
    assert p.exists() and p.name == "wm_720x1280.png"
    assert overlays.make_watermark(720, 1280, tmp_path) == p  # cache per resolusi
    im = Image.open(p).convert("RGBA")
    px = im.load()
    yellow = white = transparent = 0
    for y in range(im.height):
        for x in range(im.width):
            r, g, b, a = px[x, y]
            if a == 0:
                transparent += 1
            elif r > 200 and g > 180 and b < 90:
                yellow += 1        # SNOOPY kuning
            elif r > 240 and g > 240 and b > 240:
                white += 1         # CLIPPER putih
    assert yellow > 20 and white > 20 and transparent > 0  # dua warna + alpha


def test_fontdisplay_milky_moringa_unduh_dan_charset(tmp_path):
    """Font display pilihan owner: pastikan terunduh + PIL bisa memuatnya.
    Offline -> skip (fontdisplay.ensure toleran gagal by design)."""
    from backend import fontdisplay
    p = fontdisplay.ensure()
    if p is None:
        import pytest
        pytest.skip("font tak terunduh (offline?) — fallback Anton dipakai")
    from PIL import Image, ImageDraw, ImageFont
    f = ImageFont.truetype(p, 48)
    probe = ImageDraw.Draw(Image.new("RGBA", (8, 8)))
    assert probe.textlength("0123456789 .,!?-", font=f) > 200  # charset ada


def test_hook_png(tmp_path):
    p = overlays.make_hook("Rahasia kenapa dia cepat kaya", 720, 1280,
                           tmp_path / "hook.png")
    assert p is not None and p.exists()
    im = Image.open(p)
    assert im.width == 720 and im.height > 40    # kanvas selebar klip (center)
    assert overlays.make_hook("", 720, 1280, tmp_path / "x.png") is None


def test_deadair_segments_guard_lengkap(monkeypatch):
    monkeypatch.setattr(config, "MIN_CLIP_SEC", 0.0)  # mekanik murni, tanpa lantai
    words = [{"start": float(i), "end": i + 0.7, "text": "k"} for i in range(10)]
    for w in words[4:]:                          # sisip jeda napas 1.2s
        w["start"] += 1.2
        w["end"] += 1.2
    segs = deadair.segments(words, 0.0, 11.9)
    assert len(segs) == 2 and segs[0][1] < 3.95  # dipotong di jeda (pad 0.15)
    rapat = [{"start": 0.5 * i, "end": 0.5 * i + 0.4, "text": "k"}
             for i in range(10)]
    assert deadair.segments(rapat, 0.0, 5.0) == [(0.0, 5.0)]  # tak ada gap
    assert deadair.segments(rapat, 0.0, 2.0) == [(0.0, 2.0)]  # klip < 4s utuh
    old = config.DEADAIR
    config.DEADAIR = False
    assert deadair.segments(words, 0.0, 11.9) == [(0.0, 11.9)]  # rollback
    config.DEADAIR = old
    jarang = [{"start": 0.0, "end": 0.7, "text": "a"},
              {"start": 6.0, "end": 6.7, "text": "b"}]
    assert deadair.segments(jarang, 0.0, 7.0) == [(0.0, 7.0)]  # guard 40%/min-seg
    monkeypatch.setattr(config, "MIN_CLIP_SEC", 60.0)  # KONTRAK MIN 60 dtk:
    # hasil potong (10.7) < 60 -> jeda dipertahankan, klip utuh 11.9
    assert deadair.segments(words, 0.0, 11.9) == [(0.0, 11.9)]
    # hasil potong masih >= MIN (jeda 1.2s pada klip 61.9 -> 60.7) -> potong jalan
    w61 = [{"start": float(i), "end": i + 0.7, "text": "k"} for i in range(50)]
    for w in w61[30:]:
        w["start"] += 1.2
        w["end"] += 1.2
    segs = deadair.segments(w61, 0.0, 61.9)
    assert sum(e - s for s, e in segs) >= 60.0


def test_deadair_rebase_keyframes():
    kf = [(1.0, 100), (4.0, 200), (8.0, 300)]
    assert deadair.rebase_keyframes(kf, 3.5, 8.5) == [(0.5, 200), (4.5, 300)]
    # tak ada kf dalam rentang -> yang terdekat di-clamp ke 0 (crop tetap pintar)
    out = deadair.rebase_keyframes(kf, 9.5, 12.0)
    assert out[0][0] == 0.0 and out[0][1] == 300
    assert deadair.rebase_keyframes(None, 1.0, 2.0) is None  # crop statik lolos


def test_render_daging_penuh_visual(tmp_path):
    # render ASLI ffmpeg dengan watermark + hook + voice treatment (tanpa BGM)
    src = tmp_path / "src.mp4"
    _mkvideo(src)
    wm = overlays.make_watermark(320, 568, tmp_path)
    hk = overlays.make_hook("Rahasia Kaya Cepat", 320, 568, tmp_path / "hook.png")
    out = tmp_path / "out.mp4"
    cutter.render_clip(src, 1.0, 6.0, None, [], 320, 568, out, tmp_path,
                       wm_rel_path=wm.name, hook_rel_path=hk.name, hook_dur=2.0)
    dur = cutter.probe_duration(out)
    assert abs(dur - 5.0) < 0.35                     # durasi terjaga
    fr = tmp_path / "fr.png"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", "0.2",
                    "-i", str(out), "-frames:v", "1", str(fr)], check=True)
    im = Image.open(fr).convert("RGB")
    px = im.load()
    yellow_kiri_atas = 0
    for y in range(0, int(im.height * 0.18)):
        for x in range(0, int(im.width * 0.6)):
            r, g, b = px[x, y]
            if r > 180 and g > 150 and b < 90:
                yellow_kiri_atas += 1
    assert yellow_kiri_atas > 5     # watermark kuning TERLIHAT di kiri-atas


def test_concat_deadair_dan_bgm_pass(tmp_path):
    # dua sub-render (simulasi hasil dead-air) -> concat -> BGM pasca-concat
    src = tmp_path / "s.mp4"
    _mkvideo(src)
    subs = []
    for j, (ss, se) in enumerate([(0.0, 3.0), (4.0, 7.0)]):
        o = tmp_path / f"sub{j}.mp4"
        cutter.render_clip(src, ss, se, None, [], 320, 568, o, tmp_path)
        subs.append(o)
    merged = tmp_path / "merged.mp4"
    cutter.concat_clips(subs, merged)
    assert abs(cutter.probe_duration(merged) - 6.0) < 0.4   # 3s + 3s
    bgm = tmp_path / "bgm.wav"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
                    "-i", "sine=frequency=220:duration=3", str(bgm)], check=True)
    cutter.mix_bgm_pass(merged, {"path": bgm, "volume": 0.15}, clip_dur=6.0)
    assert abs(cutter.probe_duration(merged) - 6.0) < 0.4   # in-place, durasi utuh
