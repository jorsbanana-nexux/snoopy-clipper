"""UJI END-TO-END pipeline Snoopy Clipper (otak Gemini di-mock)."""
import os, sys, time, json
os.environ["MAX_CLIPS"] = "2"          # tes cepat
os.environ["BRAIN_MAX_FRAMES"] = "16"  # hemat
sys.path.insert(0, ".")

from backend import pipeline, brain

def mock_find_moments(transcript, duration, frames_dir=None, frame_interval=None):
    words = transcript["words"]
    if not words:
        # transkrip platform (captions): pakai baris sebagai jangkar waktu
        words = [{"start": l["start"], "end": l["end"], "text": l["text"]}
                 for l in transcript["lines"]]
    cands = []
    for k in range(0, max(1, len(words) - 10), 8):
        s = words[k]["start"]
        e = s + 22.0
        grp = [w for w in words if s <= w["start"] < e]
        cands.append((len(grp), s, e))
    cands.sort(reverse=True)
    out = []
    for cnt, s, e in cands:
        if any(s < o["end"] - 1 for o in out):
            continue
        out.append({"start": round(s, 2), "end": round(min(e, duration), 2),
                    "title": f"Momen uji {len(out)+1}", "hook": "uji hook",
                    "score": 8, "reason": "mock"})
        if len(out) == 2:
            break
    return out

brain.find_moments = mock_find_moments
print("otak di-mock: 2 momen padat kata", flush=True)

url = "https://www.youtube.com/watch?v=pf9vd2sny0M"
job_id = pipeline.create_job(url)
print("job:", job_id, flush=True)
last = None
while True:
    job = pipeline.get_job(job_id)
    key = (job["status"], job["step"], job["message"], job["pct"])
    if key != last:
        eta = job.get("eta_seconds")
        print(f"[{job['status']:7s}] {job['step']:10s} {job['pct']:3d}%  {job['message']}"
              + (f"  (ETA {int(eta)}d)" if eta else ""), flush=True)
        last = key
    if job["status"] in ("done", "error"):
        print(json.dumps({k: job[k] for k in ("status", "error", "clips")}, ensure_ascii=False, indent=1)[:800])
        break
    time.sleep(2)
sys.exit(0 if job["status"] == "done" else 1)
