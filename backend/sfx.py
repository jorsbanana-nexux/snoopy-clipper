"""SFX ringan BUKAN unduhan — disintesis via ffmpeg (100% milik Snoopy,
bebas lisensi selamanya): whoosh halus untuk awal klip & jahitan jump-cut,
pop lembut saat hook muncul. Disintesis sekali, cache permanen assets/sfx/."""
import subprocess
from pathlib import Path

_DIR = Path(__file__).resolve().parent.parent / "assets" / "sfx"


def _wav(args, out):
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error"]
                   + args + [str(out)], check=True)


def ensure():
    """Pastikan whoosh.wav + pop.wav ada (sintesis sekali, lalu cache)."""
    _DIR.mkdir(parents=True, exist_ok=True)
    whoosh = _DIR / "whoosh.wav"
    if not whoosh.exists():
        _wav(["-f", "lavfi", "-i", "anoisesrc=color=pink:duration=0.45",
              "-af", "lowpass=f=1400,highpass=f=180,"
                     "afade=t=in:st=0:d=0.22,afade=t=out:st=0.28:d=0.17"],
             whoosh)
    pop = _DIR / "pop.wav"
    if not pop.exists():
        _wav(["-f", "lavfi", "-i", "sine=frequency=700:duration=0.16",
              "-af", "afade=t=in:st=0:d=0.01,afade=t=out:st=0.015:d=0.14,"
                     "volume=1.4"],
             pop)
    return {"whoosh": whoosh, "pop": pop}
