"""
Library: klip jadi + metadata. Struktur:
  library/<video_id>/clip_01.mp4, clip_02.mp4, ...
  library/<video_id>/meta.json
"""
import json
import time
from pathlib import Path

from . import config


def video_dir(video_id: str) -> Path:
    d = config.LIBRARY_DIR / video_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def clip_path(video_id: str, clip_id: str) -> Path:
    return video_dir(video_id) / f"{clip_id}.mp4"


def save_meta(meta: dict):
    p = video_dir(meta["id"]) / "meta.json"
    p.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


def list_videos() -> list:
    out = []
    if not config.LIBRARY_DIR.exists():
        return out
    for d in config.LIBRARY_DIR.iterdir():
        if not d.is_dir():
            continue
        p = d / "meta.json"
        if not p.exists():
            continue
        try:
            out.append(json.loads(p.read_text(encoding="utf-8")))
        except Exception:
            continue
    out.sort(key=lambda m: m.get("created", 0), reverse=True)
    return out
