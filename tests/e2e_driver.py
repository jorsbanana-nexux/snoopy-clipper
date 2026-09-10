"""Driver uji E2E pipeline snoopy-clipper dengan otak-mock.

Yang DIFALSU: hanya panggilan model Gemini (_generate_with_fallback).
Yang ASLI: validasi + snap otak, download, transkrip whisper, frame,
face tracking, subtitle, potong, render, thumbnail, BGM, meta.json.
"""
import json
import os
import re
import sys
import time

os.environ["GEMINI_API_KEY"] = "mock-test-key"

from backend import config  # noqa: E402
from backend import brain  # noqa: E402


class _FakeResp:
    def __init__(self, text):
        self.text = text


def _mock_generate(client, types, parts):
    p0 = parts[0]
    ptext = getattr(p0, "text", None) or str(p0)
    m = re.search(r"Durasi: ([\d.]+) detik", ptext)
    dur = float(m.group(1)) if m else 60.0
    if dur >= 60:
        moments = [
            {"start": 8.0, "end": min(48.0, dur * 0.5),
             "title": "UJI LOOP", "hook": "tes hook menggantung...",
             "score": 9, "reason": "tes jalur loop", "trend": "evergreen",
             "audience": "tester", "bgm_mood": "tension",
             "loop": True,
             "loop_note": "bridge tes: 'dan kamu tak akan percaya'"},
            {"start": min(120.0, dur * 0.5), "end": min(160.0, dur - 5),
             "title": "UJI NORMAL", "hook": "tes klip biasa",
             "score": 8, "reason": "tes jalur non-loop", "trend": "evergreen",
             "audience": "tester", "bgm_mood": "chill",
             "loop": False, "loop_note": ""},
        ]
    else:
        moments = [
            {"start": 0.3, "end": max(dur - 0.2, 1.0),
             "title": "UJI PENDEK", "hook": "tes video pendek",
             "score": 8, "reason": "tes", "trend": "evergreen",
             "audience": "tester", "bgm_mood": "upbeat",
             "loop": True, "loop_note": "tes loop pendek"},
        ]
    return _FakeResp(json.dumps({"analysis": "mock otak", "moments": moments}))


brain._generate_with_fallback = _mock_generate

from backend import pipeline  # noqa: E402

force_no_captions = "--no-captions" in sys.argv
if force_no_captions:
    config.CAPTIONS_FIRST = False
    pipeline.captions.fetch = lambda url: None  # jamin jalur whisper

url = sys.argv[1]
t0 = time.time()
job_id = pipeline.create_job(url)
print(f"job={job_id} url={url} no_captions={force_no_captions}", flush=True)

last_step = None
while True:
    j = pipeline.get_job(job_id)
    st = j.get("status")
    step = j.get("step")
    if step != last_step:
        last_step = step
        print(f"[{time.time()-t0:7.1f}s] step={step} pct={j.get('pct')} "
              f"msg={str(j.get('message',''))[:90]}", flush=True)
    if st in ("done", "error"):
        print(f"[{time.time()-t0:7.1f}s] STATUS={st}", flush=True)
        if st == "error":
            print(str(j.get("message"))[:400], flush=True)
        else:
            clips = j.get("clips") or []
            print(f"TOTAL {time.time()-t0:.1f}s — {len(clips)} klip:", flush=True)
            for c in clips:
                print(f"  - {c['title']} | {c['start']}-{c['end']}s "
                      f"dur={c['duration']}s | loop={c['loop']} "
                      f"note={c['loop_note'][:40]} | {c['width']}x{c['height']} "
                      f"| {c['path']}", flush=True)
        break
    time.sleep(1.0)
