const $ = (s) => document.querySelector(s);
let pollTimer = null;
let etaTimer = null;

// ============ kunci API (mode hosting publik; mode lokal tak terlihat) ============
// Server dengan API_KEY terisi akan menolak request tanpa kunci.
// Simpan di localStorage, tempel sekali per browser.
function apiKey() {
  return localStorage.getItem("snoopy_key") || "";
}

async function api(url, opts = {}) {
  opts.headers = Object.assign({}, opts.headers, { "X-API-Key": apiKey() });
  const res = await fetch(url, opts);
  if (res.status === 401) {
    const k = prompt("Kunci API salah/ada. Tempel kunci yang kamu terima:");
    if (k) { localStorage.setItem("snoopy_key", k); return api(url, opts); }
  }
  return res;
}

async function ensureKey() {
  try {
    const h = await (await fetch("/api/health")).json();
    if (h.auth && !localStorage.getItem("snoopy_key")) {
      const k = prompt("Server ini terproteksi kunci API. Tempel kuncinya:");
      if (k) localStorage.setItem("snoopy_key", k);
    }
  } catch { /* offline: biarkan, alert error lama yang bicara */ }
}

// Semua teks job/library bisa berasal dari judul, channel, atau error extractor
// eksternal. Jangan pernah masukkan mentah ke innerHTML.
function esc(value) {
  return String(value ?? "").replace(/[&<>'"]/g, (ch) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;",
  }[ch]));
}

function apiAsset(value) {
  const path = String(value || "");
  return path.startsWith("/api/") ? esc(path) : "";
}

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
    const res = await api("/api/clip", {
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
      job = await (await api(`/api/jobs/${jobId}`)).json();
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
  const err = job.status === "error"
    ? `<p class="error">${esc(job.error || job.message || "")}</p>` : "";
  const pct = job.status === "done" ? 100 : job.pct || 0;
  $("#job").innerHTML = `
    ${job.video ? `<h3>${esc(job.video.title)}</h3>` : ""}
    <div class="bar"><div class="fill" style="width:${pct}%"></div></div>
    <p class="msg">${esc(job.message || "")}</p>
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

// ============ Publish ke YouTube Shorts ============
async function publishClip(btn) {
  btn.disabled = true; btn.textContent = "Mengunggah…";
  try {
    const res = await api(`/api/publish/${btn.dataset.v}/${btn.dataset.c}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title: btn.dataset.t, description: btn.dataset.h }),
    });
    if (!res.ok) {
      const e = await res.json().catch(() => ({}));
      const msg = e.detail || "Gagal upload";
      if (String(msg).includes("authorize")) {
        // belum pernah izinkan YouTube -> buka tab izin Google otomatis
        const a = await (await api("/api/publish/authorize")).json().catch(() => ({}));
        if (a.url) { window.open(a.url, "_blank"); alert("Tab izin YouTube terbuka — setujui aksesnya lalu klik Publish lagi di sini."); }
        else alert(msg);
      } else alert(msg);
      btn.disabled = false; btn.textContent = "Publish ke YT";
      return;
    }
    const { url } = await res.json();
    btn.textContent = "Tayang ✓";
    window.open(url, "_blank");
  } catch {
    alert("Tidak bisa menghubungi server.");
    btn.disabled = false; btn.textContent = "Publish ke YT";
  }
}

async function loadLibrary() {
  let data;
  try {
    data = await (await api("/api/library")).json();
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
      <h3>${esc(v.title)}</h3>
      <p class="meta">${new Date(v.created * 1000).toLocaleDateString("id-ID")} · ${Number(v.clips?.length || 0)} klip${v.uploader ? " · " + esc(v.uploader) : ""}</p>
      <div class="clips">
        ${(v.clips || []).map((c) => `
          <div class="clip">
            <video src="${apiAsset(c.path)}" poster="${apiAsset(c.thumb)}" preload="metadata" controls playsinline></video>
            <div class="clip-info">
              <b>${esc(c.title)}</b>
              ${c.hook ? `<span class="hook">${esc(c.hook)}</span>` : ""}
              <span class="score">★ ${esc(c.score)}</span>
              ${c.loop ? `<span class="loop-badge" title="${esc(c.loop_note || "Kalimat akhir menyambung ke hook awal — klip enak diputar ulang.")}">∞ Loop alami</span>` : ""}
              <span>${esc(c.duration)}s · ${esc(c.width)}x${esc(c.height)}</span>
              ${c.bgm ? `<span class="bgm-credit">${esc(c.bgm)}</span>` : ""}
              <a class="dl" href="${apiAsset(c.path)}" download>Download MP4</a>
              <button class="dl pub" data-v="${esc(v.id)}" data-c="${esc(c.id)}"
                      data-t="${esc(c.title)}" data-h="${esc(c.hook || "")}">Publish ke YT</button>
            </div>
          </div>`).join("")}
      </div>
    </div>`).join("");
  wrap.querySelectorAll(".pub").forEach((b) => b.addEventListener("click", () => publishClip(b)));
}

ensureKey().then(loadLibrary);
$("#go").addEventListener("click", startJob);
$("#url").addEventListener("keydown", (e) => {
  if (e.key === "Enter") startJob();
});
