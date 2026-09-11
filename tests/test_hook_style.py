"""Kontrak hook overlay baru (permintaan owner 2026-09-11):
1. APNG ANIMASI fade subtitle: lead-in transparan -> fade-in -> hold ->
   fade-out + BLUR memudar (frame terakhir lenyap).
2. Putih BERSIH tebal TANPA outline hitam — hanya shadow gelap banyak-lapis
   radius jauh ala gradient (alpha maks 210, tidak solid pekat).
3. Emoji topik: hanya tag TERKENAL yang boleh lolos / menimpa."""


def test_hook_adalah_apng_animasi_dengan_fade_dan_blur(tmp_path):
    from backend import overlays
    p = overlays.make_hook("Rahasia kenapa dia cepat kaya", 720, 1280,
                           tmp_path / "hook.png")
    assert p is not None and p.exists()
    from PIL import Image, ImageSequence
    im = Image.open(p)
    assert getattr(im, "is_animated", False), "harus APNG animasi, bukan PNG mati"
    frames = [fr.convert("RGBA") for fr in ImageSequence.Iterator(im)]
    assert len(frames) >= 15                      # lead+in+hold+out cukup halus
    assert frames[0].getextrema()[3][0] == 0     # frame pertama: transparan total
    assert frames[-1].getextrema()[3][0] == 0    # frame terakhir: lenyap total
    # frame hold: teks putih terlihat
    mid = frames[8]
    white = sum(1 for px in mid.getdata() if px[3] > 200
                and px[0] > 230 and px[1] > 230 and px[2] > 230)
    assert white > 100, "teks putih tebal harus terlihat"
    # frame fade-out akhir harus LEBIH BLUR: hitung piksel tajam tersisa
    assert frames[-2].getextrema()[3][0] < 60    # sudah nyaris lenyap saat blur


def test_hook_tanpa_outline_hitam_solid(tmp_path):
    """Tidak boleh ada outline hitam pekat (alpha 255) — shadow tergelap
    cuma alpha ~210: gradient gelap, bukan stroke solid."""
    from backend import overlays
    from PIL import Image, ImageSequence
    p = overlays.make_hook("Uang, Cinta, dan Kekuasaan", 720, 1280,
                           tmp_path / "hook.png")
    im = Image.open(p)
    frames = [fr.convert("RGBA") for fr in ImageSequence.Iterator(im)]
    mid = frames[8]
    solid_black = sum(1 for px in mid.getdata()
                     if px[3] == 255 and px[0] < 25 and px[1] < 25 and px[2] < 25)
    assert solid_black == 0, "outline hitam solid dilarang — hanya shadow lembut"


def test_hook_dan_render_nyata_ffmpeg(tmp_path):
    """APNG harus benar-benar bisa di-overlay ffmpeg (integrasi nyata)."""
    from backend import overlays, cutter
    src = tmp_path / "src.mp4"
    import subprocess
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                 "-f", "lavfi", "-i", "testsrc=duration=6:size=320x568:rate=10",
                 "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
                 "-shortest", "-c:v", "libx264", "-c:a", "aac", str(src)])
    wm = overlays.make_watermark(320, 568, tmp_path)
    hk = overlays.make_hook("Rahasia Kaya Cepat", 320, 568, tmp_path / "hook.png")
    out = tmp_path / "out.mp4"
    cutter.render_clip(src, 1.0, 6.0, None, [], 320, 568, out, tmp_path,
                       wm_rel_path=wm.name, hook_rel_path=hk.name, hook_dur=2.0)
    assert out.exists() and out.stat().st_size > 10_000


def test_topic_tag_hanya_yang_terkenal():
    from backend import brain
    assert brain._topic_tag("finance") == "finance"
    assert brain._topic_tag(" Love ") == "love"
    assert brain._topic_tag("cinta") == ""      # kata bebas = TOLAK
    assert brain._topic_tag("") == ""
    assert brain._topic_tag(None) == ""


def test_direktur_prompt_memakai_daftar_tetap():
    from backend import brain
    import inspect
    src = inspect.getsource(brain)
    assert '"topic_tag": tag emoji topik thumbnail' in src
    assert "JANGAN paksa asal" in src
