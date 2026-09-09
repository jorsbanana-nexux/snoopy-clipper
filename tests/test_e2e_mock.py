"""Smoke test URL nyata yang hanya jalan bila dipanggil secara eksplisit.

File ini sengaja *bukan* tes pytest biasa. Versi sebelumnya membuat job, mengunduh
video, dan merender saat modul di-*import* oleh pytest. Itu menjadikan ``pytest``
berbahaya di PC low-spec dan membuat CI tidak deterministis.

Jalankan manual, dengan sadar akan bandwidth dan waktu render:
    python tests/test_e2e_mock.py https://www.youtube.com/watch?v=<video_id>
"""
import json
import os
import sys
import time


def mock_find_moments(transcript, duration, frames_dir=None, frame_interval=None, meta=None):
    """Pengganti Gemini deterministis untuk menguji IO/render URL nyata."""
    words = transcript["words"]
    if not words:
        words = [{"start": line["start"], "end": line["end"], "text": line["text"]}
                 for line in transcript["lines"]]
    candidates = []
    for k in range(0, max(1, len(words) - 10), 8):
        start = words[k]["start"]
        end = start + 22.0
        group = [word for word in words if start <= word["start"] < end]
        candidates.append((len(group), start, end))
    candidates.sort(reverse=True)
    output = []
    for _, start, end in candidates:
        if any(start < chosen["end"] - 1 for chosen in output):
            continue
        output.append({
            "start": round(start, 2), "end": round(min(end, duration), 2),
            "title": f"Momen smoke {len(output) + 1}", "hook": "uji hook",
            "score": 8, "reason": "mock",
        })
        if len(output) == 2:
            break
    return output


def run_remote_smoke(url: str) -> int:
    # Import di sini supaya pytest tidak pernah membangun job secara tidak sengaja.
    from backend import brain, pipeline

    brain.find_moments = mock_find_moments
    job_id = pipeline.create_job(url)
    print(f"job: {job_id}", flush=True)
    last = None
    while True:
        job = pipeline.get_job(job_id)
        key = (job["status"], job["step"], job["message"], job["pct"])
        if key != last:
            eta = job.get("eta_seconds")
            print(f"[{job['status']:7s}] {job['step']:10s} {job['pct']:3d}%  {job['message']}"
                  + (f" (ETA {int(eta)}d)" if eta else ""), flush=True)
            last = key
        if job["status"] in ("done", "error"):
            print(json.dumps({key: job[key] for key in ("status", "error", "clips")},
                             ensure_ascii=False, indent=1)[:1200])
            return 0 if job["status"] == "done" else 1
        time.sleep(2)


if __name__ == "__main__":
    os.environ.setdefault("MAX_CLIPS", "2")
    os.environ.setdefault("BRAIN_MAX_FRAMES", "16")
    sys.path.insert(0, ".")
    target = (sys.argv[1] if len(sys.argv) > 1
              else "https://www.youtube.com/watch?v=pf9vd2sny0M")
    raise SystemExit(run_remote_smoke(target))
