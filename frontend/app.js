const $ = (s) => document.querySelector(s);
let pollTimer = null;
let etaTimer = null;

// Hitung-mundur ETA LIVE di sisi browser: backend hanya mengirim estimasi saat
// pesan baru muncul; di antara itu angka tick turun sendiri tiap detik —
// jadi "Sisa waktu" tidak pernah tampak beku walau fase sedang berjalan lama.
function startEtaTicker(etaSeconds) {
  clearInterval(etaTimer);
  if (etaSeconds == null || isNaN(etaSeconds) || etaSeconds <= 0) return;
  const recvAt = Date.now();
  etaTimer = setInterval(() => {
    const el = $("#eta");
    if (!el) return;
    const left = etaSeconds - (Date.now() - recvAt) / 1000;
    el.textContent = left > 0 ? fmtEta(left) : "sebentar lagi…";
  }, 1000);
}

const STEPS = [
  ["info", "Info video"],
  ["captions", "Transkrip platform (instan)"],
  ["download", "Unduh video"],
  ["audio", "Siapkan audio"],
  ["transcribe", "Transkripsi Whisper"],
  ["frames", "Cuplikan frame"],
  ["brain", "AI pilih momen (Gemini)"],
  ["render", "Render klip"],
];

function fmtEta(sec) {
  if (sec == null || isNaN(sec)) return "menghitung…";
  if (sec < 1) return "selesai";
  const m = Math.floor(sec / 60);
  const s = Math.round(sec % 60);
  return m > 0 ? `~${m} mnt ${s} dtk` : `~${s} dtk`;
}

async function startJob() {
  const url = $("#url").value.trim();
  if (!/^https?:\/\//.test(url)) {
    alert("Tempel URL video dulu (harus diawali https://)");
    return;
  }
  $("#go").disabled = true;
  try {
    const res = await fetch("/api/clip", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
    });
    if (!res.ok) {
      const e = await res.json().catch(() => ({}));
      alert(e.detail || "Gagal memulai job");
      $("#go").disabled = false;
      return;
    }
    const { job_id } = await res.json();
    $("#job").classList.remove("hidden");
    $("#job").innerHTML = `<p class="msg">Memulai…</p>`;
    poll(job_id);
  } catch {
    alert("Tidak bisa menghubungi server.");
    $("#go").disabled = false;
  }
}

function poll(jobId) {
  clearInterval(pollTimer);
  pollTimer = setInterval(async () => {
    let job;
    try {
      job = await (await fetch(`/api/jobs/${jobId}`)).json();
    } catch {
      return;
    }
    renderJob(job);
    if (job.status === "done" || job.status === "error") {
      clearInterval(pollTimer);
      clearInterval(etaTimer);
      $("#go").disabled = false;
      if (job.status === "done") loadLibrary();
    }
  }, 1200);
}

function renderJob(job) {
  const order = STEPS.map(([k]) => k);
  const idx = order.indexOf(job.step);
  const stepsHtml = STEPS.map(([key, label], i) => {
    let cls = "step";
    if (job.status === "done" || (i < idx)) cls += " ok";
    else if (i === idx && job.status !== "done") cls += " active";
    return `<div class="${cls}">${label}</div>`;
  }).join("");
  const err = job.status === "error" ? `<p class="error">${job.error || job.message || ""}</p>` : "";
  const pct = job.status === "done" ? 100 : job.pct || 0;
  $("#job").innerHTML = `
    ${job.video ? `<h3>${job.video.title}</h3>` : ""}
    <div class="bar"><div class="fill" style="width:${pct}%"></div></div>
    <p class="msg">${job.message || ""}</p>
    ${job.status !== "error" && job.status !== "done"
        ? `<p class="eta">Sisa waktu: <b id="eta">${fmtEta(job.eta_seconds)}</b> · ${pct}%</p>`
        : ""}
    <div class="steps">${stepsHtml}</div>
    ${err}
  `;
  if (job.status !== "error" && job.status !== "done") {
    startEtaTicker(job.eta_seconds);
  }
}

async function loadLibrary() {
  let data;
  try {
    data = await (await fetch("/api/library")).json();
  } catch {
    return;
  }
  const wrap = $("#library");
  if (!data.videos.length) {
    wrap.innerHTML = `<p class="empty">Belum ada klip. Tempel URL di atas lalu klik GetClips.</p>`;
    return;
  }
  wrap.innerHTML = data.videos.map((v) => `
    <div class="video">
      <h3>${v.title}</h3>
      <p class="meta">${new Date(v.created * 1000).toLocaleDateString("id-ID")} · ${v.clips.length} klip${v.uploader ? " · " + v.uploader : ""}</p>
      <div class="clips">
        ${v.clips.map((c) => `
          <div class="clip">
            <video src="${c.path}" preload="metadata" controls playsinline></video>
            <div class="clip-info">
              <b>${c.title}</b>
              <span class="score">★ ${c.score}</span>
              <span>${c.duration}s · ${c.width}x${c.height}</span>
              ${c.bgm ? `<span class="bgm-credit">${c.bgm}</span>` : ""}
              <a class="dl" href="${c.path}" download>Download MP4</a>
            </div>
          </div>`).join("")}
      </div>
    </div>`).join("");
}

loadLibrary();
$("#go").addEventListener("click", startJob);
$("#url").addEventListener("keydown", (e) => {
  if (e.key === "Enter") startJob();
});
