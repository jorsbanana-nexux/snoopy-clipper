"""Uji render FFmpeg nyata pada video kecil, tanpa jaringan atau model AI."""
import subprocess

from backend import config, cutter


def test_render_has_vertical_video_and_full_audio(tmp_path, monkeypatch):
    source = tmp_path / "source.mp4"
    output = tmp_path / "clip.mp4"
    subprocess.run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=12:duration=2",
        "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100:duration=2",
        "-shortest", "-pix_fmt", "yuv420p", str(source),
    ], check=True)
    monkeypatch.setattr(config, "MOTION_BLUR", False)
    monkeypatch.setattr(config, "GAME_ULTRA", False)
    monkeypatch.setattr(
        cutter, "_encoder",
        (["-c:v", "libx264", "-preset", "ultrafast", "-crf", "30"], "test"),
    )
    width, height, _ = cutter.render_clip(
        source, 0.0, 2.0, "", [(0.0, 320.0), (2.0, 320.0)], 640, 360,
        output, tmp_path,
    )
    assert (width, height) == (720, 1280)
    assert output.exists() and output.stat().st_size > 10_000
    assert cutter.probe_duration(output) > 1.5
    assert cutter.av_duration_check(output) is None
