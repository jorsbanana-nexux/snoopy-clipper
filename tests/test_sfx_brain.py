"""SFX sintesis (whoosh + pop) + STANDAR AKHIR otak: kurasi skor minimum &
uji 'berhenti scroll' di prompt. Kontrak: tanpa BGM & tanpa SFX yang bisa
dicampur -> pass no-op (file tak tersentuh)."""
import subprocess

from backend import brain, config, cutter, sfx


def _mkvideo(path, dur=2.0, w=320, h=568):
    subprocess.run(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
         "-f", "lavfi", "-i", f"testsrc2=size={w}x{h}:rate=24:duration={dur}",
         "-f", "lavfi", "-i", f"sine=frequency=440:duration={dur}",
         "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
         "-c:a", "aac", str(path)], check=True)


def test_sfx_disintesis_dan_dicache(tmp_path, monkeypatch):
    monkeypatch.setattr(sfx, "_DIR", tmp_path)
    a = sfx.ensure()
    assert a["whoosh"].exists() and a["pop"].exists()
    assert a["whoosh"].stat().st_size > 1000 and a["pop"].stat().st_size > 500
    assert sfx.ensure()["whoosh"] == a["whoosh"]        # cache: tak sintesis ulang
    d = cutter.probe_duration(a["whoosh"])
    assert 0.3 < d < 0.7                                 # whoosh singkat halus
    d2 = cutter.probe_duration(a["pop"])
    assert 0.05 < d2 < 0.3


def test_mix_pass_sfx_tanpa_bgm_dan_noop(tmp_path):
    out = tmp_path / "o.mp4"
    _mkvideo(out)
    cutter.mix_bgm_pass(out, None, sfx_times=[0.0], hook_pop=True, clip_dur=2.0)
    assert abs(cutter.probe_duration(out) - 2.0) < 0.35  # durasi terjaga
    # tak ada BGM/SFX -> NO-OP: file tak tersentuh
    before = out.read_bytes()
    cutter.mix_bgm_pass(out, None, clip_dur=2.0)
    assert out.read_bytes() == before
    # SFX dimatikan via config -> no-op juga
    old = config.SFX
    config.SFX = False
    cutter.mix_bgm_pass(out, None, sfx_times=[0.0], hook_pop=True, clip_dur=2.0)
    assert out.read_bytes() == before
    config.SFX = old


def test_mix_pass_bgm_dan_sfx_bareng(tmp_path):
    out = tmp_path / "o.mp4"
    _mkvideo(out)
    bgm = tmp_path / "bgm.wav"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
                    "-i", "sine=frequency=220:duration=3", str(bgm)], check=True)
    cutter.mix_bgm_pass(out, {"path": bgm, "volume": 0.15},
                        sfx_times=[0.0, 1.0], hook_pop=True, clip_dur=2.0)
    assert abs(cutter.probe_duration(out) - 2.0) < 0.35  # BGM + 2 whoosh + pop


def test_brain_standar_akhir_dan_kurasi_skor():
    tr = {"lines": [{"start": 0.0, "end": 2.0, "text": "tes"}], "language": "id"}
    p = brain._build_prompt(tr, 60.0, [], None, meta={"title": "t", "uploader": "u"})
    assert "STANDAR AKHIR" in p and "BERHENTI scroll" in p
    assert "ARC MINI" in p and "KURASI" in p
    # momen datar (skor rendah) DITOLAK; momen menarik lolos
    moments = [
        {"start": 1.0, "end": 30.0, "title": "datar", "score": 3},
        {"start": 40.0, "end": 70.0, "title": "menarik", "score": 9},
    ]
    out = brain._validate(moments, [], 120.0)
    assert len(out) == 1 and out[0]["title"] == "menarik"
    # floor bisa dinaikkan via .env
    old = config.MIN_CLIP_SCORE
    config.MIN_CLIP_SCORE = 9.5
    out = brain._validate(moments, [], 120.0)
    assert out == []                                       # semua di bawah floor
    config.MIN_CLIP_SCORE = old
