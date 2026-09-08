"""
Face tracking v3 — PEMBICARA AKTIF, dukungan 2..10+ orang, mulus tanpa kacau.
Kunci utamanya: ini OFFLINE (kita tahu seluruh timeline SEBELUM render),
jadi kamera tidak pernah telat — dan fokusnya adalah PEMBICARA AKTIF.

Cara kerja:
1. Deteksi SEMUA wajah + landmark mulut (YuNet) tiap FACE_SAMPLE_INTERVAL detik.
2. Wajah di-track antar sampel — matching JARAK GLOBAL (semua pasangan
   diurut dari terdekat), jadi identitas terjaga walau banyak wajah rapat.
3. "Siapa yang bicara" dinilai dari gerakan mulut (variance window +-2).
4. SEGMENT BICARA: skor sesaat dihimpun jadi segmen berkelanjutan.
   Ganti fokus HANYA jika pembicara baru MENAHAN bicara >= SPEAKER_SWITCH_SEC
   -> balasan singkat "oke"/"ya" (backchannel) DIABAIKAN, kamera tenang.
5. SEREMPAK: dua+ orang bicara bersamaan -> pindah hanya kalau JELAS lebih
   dominan (SPEAKER_DOMINANCE x) -> tidak ada flip-flop kamera.
6. Pembicara aktif hilang dari frame -> serahkan mulus ke pembicara aktif
   lain / wajah dominan yang terlihat. Tidak ada yang bicara -> wajah
   dominan (terbesar & paling terlihat), bukan loncat acak.
7. LOOK-AHEAD: transisi S-curve (C1) ke pembicara berikutnya dimulai
   LEAD_AHEAD_SEC detik sebelum flip — kamera menyorot duluan.
8. Smoothing zero-phase (EMA maju-mundur) + clamp kecepatan ->
   tidak teleport, tidak overshoot, tidak kaku.
"""
import urllib.request

from . import config

_MODEL_URL = (
    "https://github.com/opencv/opencv_zoo/raw/main/"
    "models/face_detection_yunet/face_detection_yunet_2023mar.onnx"
)
_INFER_W, _INFER_H = 192, 144  # cukup besar untuk landmark mulut akurat, tetap ringan
_N_BANDS = 12  # band horizontal untuk profil saliency & teks-bawaan


def _model_path():
    p = config.MODELS_DIR / "face_detection_yunet_2023mar.onnx"
    if not p.exists():
        urllib.request.urlretrieve(_MODEL_URL, p)
    return p


def get_dims(video_path):
    import cv2
    cap = cv2.VideoCapture(str(video_path))
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()
    return w, h


def _band_profiles(edges):
    """Profil per band horizontal (12 band) dari peta edge:
    - saliency: kepadatan edge (area yang menarik mata / objek utama)
    - teks-bawaan: banyak komponen kecil teratur = baris teks (pengganti OCR ringan)
    """
    import cv2
    bh = max(1, edges.shape[0] // _N_BANDS)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(edges)
    comps = [(stats[i, cv2.CC_STAT_LEFT], stats[i, cv2.CC_STAT_TOP],
              stats[i, cv2.CC_STAT_WIDTH], stats[i, cv2.CC_STAT_HEIGHT])
             for i in range(1, n)]
    sal, txt = [], []
    for r in range(_N_BANDS):
        band = edges[r * bh:(r + 1) * bh]
        sal.append(float(band.mean()) / 255.0)
        # stroke huruf di resolusi kecil: komponen tipis pendek (h 2-6px, w 2-18px)
        cnt = sum(1 for (cx0, cy0, cw, chh) in comps
                  if r * bh <= cy0 + chh / 2 < (r + 1) * bh
                  and 2 <= chh <= 6 and 2 <= cw <= 18)
        txt.append(min(1.0, cnt / 40.0))
    return sal, txt


def sample_faces(video_path, times: list) -> list:
    """
    Sampling wajah pada detik-detik tertentu (SEMUA wajah, bukan cuma terbesar).
    Bonus per frame (numpang pass yang sama, biaya nyaris nol) untuk placement:
    - "sal": profil saliency 12 band (area yang menarik perhatian mata)
    - "txt": indikasi teks-bawaan video (baris komponen kecil teratur)
    - "box": bounding box tiap wajah dalam FRAKSI frame (untuk collision subtitle)
    -> [{"t": t, "faces": [...], "sal": [...], "txt": [...]}]
    """
    import cv2
    detector = cv2.FaceDetectorYN.create(
        str(_model_path()), "", (_INFER_W, _INFER_H), score_threshold=0.5
    )
    cap = cv2.VideoCapture(str(video_path))
    samples = []
    for t in times:
        cap.set(cv2.CAP_PROP_POS_MSEC, max(0.0, t) * 1000)
        ok, frame = cap.read()
        if not ok or frame is None or frame.shape[0] == 0:
            samples.append({"t": t, "faces": [], "sal": None, "txt": None})
            continue
        h, w = frame.shape[:2]
        if w == 0 or h == 0:
            samples.append({"t": t, "faces": [], "sal": None, "txt": None})
            continue
        small = cv2.resize(frame, (_INFER_W, _INFER_H))
        # analisis band: saliency + indikasi teks-bawaan
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(cv2.GaussianBlur(gray, (3, 3), 0), 40, 120)
        sal, txt = _band_profiles(edges)
        # deteksi wajah
        res = detector.detect(small)
        raw = res[1] if res is not None else None
        faces = []
        if raw is not None:
            for f in raw:
                x, y, fw, fh = [float(v) for v in f[:4]]
                rm_x, rm_y, lm_x, lm_y = float(f[10]), float(f[11]), float(f[12]), float(f[13])
                mouth = ((rm_x - lm_x) ** 2 + (rm_y - lm_y) ** 2) ** 0.5 / max(fw, 1.0)
                faces.append({
                    "cx": (x + fw / 2) / _INFER_W * w,
                    "cy": (y + fh / 2) / _INFER_H,
                    "fw": fw, "fh": fh,
                    "mouth": mouth, "det": float(f[14]),
                    "box": (x / _INFER_W, y / _INFER_H,
                            (x + fw) / _INFER_W, (y + fh) / _INFER_H),
                })
        samples.append({"t": t, "faces": faces, "sal": sal, "txt": txt})
    cap.release()
    return samples


def _vision_summary(samples: list) -> dict:
    """Rangkuman data vision untuk placement (rata-rata antar sampel)."""
    sal_rows = [s["sal"] for s in samples if s["sal"]]
    txt_rows = [s["txt"] for s in samples if s["txt"]]
    avg = lambda rows: [sum(col) / len(col) for col in zip(*rows)] if rows else []
    return {
        "sal": avg(sal_rows),
        "txt": avg(txt_rows),
        "boxes": [(s["t"], [f["box"] for f in s["faces"]]) for s in samples],
        "interval": config.FACE_SAMPLE_INTERVAL,
    }


# ---------------- tracking & fokus ----------------

def _build_tracks(samples: list, src_w: int) -> list:
    """Matching antar sampel -> track wajah konsisten. Semua pasangan
    (wajah x track) diurut dari jarak TERDEKAT dulu -> identitas terjaga
    walau 10 wajah bergerak rapat (greedy per-wajah bisa salah pasang)."""
    max_jump = src_w * 0.25
    tracks = []
    for si, s in enumerate(samples):
        pairs = []
        for fi, f in enumerate(s["faces"]):
            for ti, tr in enumerate(tracks):
                last_si, last_f = tr["points"][-1]
                if si - last_si > 3:  # track sudah lama hilang -> dianggap mati
                    continue
                d = abs(f["cx"] - last_f["cx"]) + abs(f["cy"] - last_f["cy"]) * src_w
                if d < max_jump:
                    pairs.append((d, fi, ti))
        pairs.sort()
        used_f, used_t = set(), set()
        for d, fi, ti in pairs:
            if fi in used_f or ti in used_t:
                continue
            tracks[ti]["points"].append((si, s["faces"][fi]))
            used_f.add(fi)
            used_t.add(ti)
        for fi in range(len(s["faces"])):  # wajah baru masuk frame
            if fi not in used_f:
                tracks.append({"points": [(si, s["faces"][fi])], "speak": {}})
    min_pts = max(2, int(len(samples) * 0.08))
    return [t for t in tracks if len(t["points"]) >= min_pts]


def _speaking_score(track: dict):
    """Skor 'sedang bicara' per titik: variance gerak mulut (window +-2 sampel), relatif.
    (Window +-3 membuat deteksi ganti pembicara telat +-3 dtk pada sampling 1 dtk
     -> kamera masih menyorot pembicara LAMA beberapa detik setelah ganti -> wajah
     pembicara baru terpotong. +-2 = deteksi lebih gesit, tetap stabil dgn hysteresis.)"""
    mouths = [(si, f["mouth"]) for si, f in track["points"]]
    for si, f in track["points"]:
        win = [m for s2, m in mouths if abs(s2 - si) <= 2]
        if len(win) < 2:
            track["speak"][si] = 0.0
            continue
        mean = sum(win) / len(win)
        var = sum((m - mean) ** 2 for m in win) / len(win)
        track["speak"][si] = var / (mean * mean + 1e-6)


def _segments_of(track: dict, n: int, th: float) -> list:
    """Himpun skor mulut sesaat jadi SEGMENT bicara berkelanjutan [(s0, s1)]."""
    segs, s = [], None
    for si in range(n):
        if track["speak"].get(si, 0.0) >= th:
            if s is None:
                s = si
        elif s is not None:
            segs.append((s, si - 1))
            s = None
    if s is not None:
        segs.append((s, n - 1))
    return segs


def _active_at(track: dict, si: int) -> tuple:
    """Segment bicara yang menutupi si (None kalau sedang diam)."""
    for seg in track["_segs"]:
        if seg[0] <= si <= seg[1]:
            return seg
    return None


def _recently_active(track: dict, si: int) -> bool:
    """Aktif pada si atau si-1 — meredam kedip sesaat antar kata."""
    return _active_at(track, si) is not None or (si > 0 and _active_at(track, si - 1) is not None)


def _visible_at(track: dict, si: int, back: int = 2) -> bool:
    """Track masih terlihat di sekitar si (ada titik deteksi)."""
    return any(abs(s - si) <= back for s, _ in track["points"])


def _dominant_visible(tracks: list, si: int):
    """Wajah paling besar yang TERLIHAT saat si (dominan nyata, bukan acak)."""
    best, best_sc = None, -1.0
    for ti, tr in enumerate(tracks):
        if not _visible_at(tr, si):
            continue
        sc = max((f["fw"] for s, f in tr["points"] if abs(s - si) <= 2), default=0.0)
        if sc > best_sc:
            best_sc, best = sc, ti
    return best


def _focus_timeline(tracks: list, n: int) -> list:
    """FOKUS = PEMBICARA AKTIF — mendukung jumlah orang berapa pun (2, 3, 10+).

    - Ganti fokus HANYA kalau pembicara baru MENAHAN bicara
      >= SPEAKER_SWITCH_SEC ("oke"/"ya" singkat = backchannel -> diabaikan).
    - Bicara serempak: pindah hanya kalau JELAS lebih dominan
      (SPEAKER_DOMINANCE x) -> kamera tidak flip-flop.
    - Giliran bicara sungguhan (pembicara lama berhenti & baru menahan) ->
      pindah LANGSUNG, mulus lewat look-ahead.
    - Pembicara hilang dari frame -> serahkan ke pembicara aktif lain,
      kalau tidak ada -> wajah dominan yang terlihat.
    - Tidak ada yang bicara sepanjang klip -> wajah dominan paling besar.
    """
    import math
    th = config.SPEAKER_MIN_ACTIVITY
    # minimal 3 sampel: window skor mulut melebar +-2 sampel, jadi interjeksi
    # singkat "oke"/"ya" bisa menghasilkan segmen 4-5 sampel palsu — konfirmasi
    # 3 sampel berkelanjutan menyaringnya (giliran sungguhan tetap gesit).
    switch_n = max(3, math.ceil(config.SPEAKER_SWITCH_SEC / config.FACE_SAMPLE_INTERVAL))
    dom_ratio = max(1.05, config.SPEAKER_DOMINANCE)
    for tr in tracks:
        tr["_segs"] = _segments_of(tr, n, th)
    focus = []
    cur = None
    for si in range(n):
        # kandidat: track yang SEDANG menahan bicara cukup lama
        cands = []
        for ti, tr in enumerate(tracks):
            seg = _active_at(tr, si)
            if seg and si - seg[0] + 1 >= switch_n:
                cands.append((tr["speak"].get(si, 0.0), ti))
        # skor tertinggi dulu; seri -> track paling dulu mapan (deterministik,
        # tidak loncat acak saat banyak orang bicara serempak sama rata)
        cands.sort(key=lambda c: (c[0], -c[1]), reverse=True)
        if cur is None:
            if cands:
                cur = cands[0][1]  # pembicara pertama yang menahan bicara
        elif cands and cands[0][1] != cur:
            b_sc, b_ti = cands[0]
            if not _recently_active(tracks[cur], si):
                cur = b_ti  # giliran bicara pindah: pembicara lama sudah diam
            elif b_sc > tracks[cur]["speak"].get(si, 0.0) * dom_ratio:
                cur = b_ti  # serempak: hanya kalau jelas lebih dominan
        # pembicara aktif hilang dari frame & tidak ada kandidat menahan
        if cur is not None and not _visible_at(tracks[cur], si) and not cands:
            nxt = _dominant_visible(tracks, si)
            if nxt is not None and nxt != cur:
                cur = nxt
        focus.append(cur)
    # backfill awal: sebelum pembicara pertama menahan bicara, kamera SUDAH
    # siap menyorot dia sejak awal (offline — kita tahu masa depan timeline)
    for i, x in enumerate(focus):
        if x is not None:
            for j in range(i):
                focus[j] = x
            break
    # fallback: tidak ada yang bicara sepanjang klip -> wajah dominan
    if all(f is None for f in focus) and tracks:
        dom = max(range(len(tracks)),
                  key=lambda ti: sum(f["fw"] for _, f in tracks[ti]["points"]))
        focus = [dom] * n
    return focus


def _center_at(track: dict, si: int) -> float:
    """Posisi cx track pada sampel si (interpolasi; ekstrapapasi ke titik terdekat)."""
    pts = track["points"]
    if si <= pts[0][0]:
        return pts[0][1]["cx"]
    if si >= pts[-1][0]:
        return pts[-1][1]["cx"]
    for k in range(len(pts) - 1):
        (s0, f0), (s1, f1) = pts[k], pts[k + 1]
        if s0 <= si <= s1:
            if s1 == s0:
                return f0["cx"]
            r = (si - s0) / (s1 - s0)
            return f0["cx"] + (f1["cx"] - f0["cx"]) * r
    return pts[-1][1]["cx"]


def _cy_at(track: dict, si: int) -> float:
    """Posisi vertikal (fraksi) track pada sampel si — untuk penempatan subtitle."""
    pts = track["points"]
    if si <= pts[0][0]:
        return pts[0][1]["cy"]
    if si >= pts[-1][0]:
        return pts[-1][1]["cy"]
    for k in range(len(pts) - 1):
        (s0, f0), (s1, f1) = pts[k], pts[k + 1]
        if s0 <= si <= s1:
            if s1 == s0:
                return f0["cy"]
            r = (si - s0) / (s1 - s0)
            return f0["cy"] + (f1["cy"] - f0["cy"]) * r
    return pts[-1][1]["cy"]


def _fill_nearest(xs: list):
    valid = [i for i, v in enumerate(xs) if v is not None]
    if not valid:
        return
    for i in range(len(xs)):
        if xs[i] is None:
            xs[i] = xs[min(valid, key=lambda j: abs(j - i))]


def _focus_path(samples, tracks, focus, lead_sec, interval):
    """Path target per sampel + LOOK-AHEAD: aim ke pembicara berikutnya LEBIH AWAL."""
    n = len(samples)
    times = [s["t"] for s in samples]
    tx = [None] * n
    ty = [None] * n
    for si, fti in enumerate(focus):
        if fti is not None:
            tx[si] = _center_at(tracks[fti], si)
            ty[si] = _cy_at(tracks[fti], si)
    _fill_nearest(tx)
    _fill_nearest(ty)
    # LOOK-AHEAD TRANSISI ditanam di path MENTAH (sebelum smoothing):
    # S-curve smoothstep (C1) ke pembicara berikutnya, selesai 2 sampel sebelum
    # flip terdeteksi (antisipasi lag window skor bicara +-2 sampel). Karena
    # transisi menggantikan step mentah, EMA tidak punya 'step response' yang
    # bisa membekas sebagai lesi dip / kamera merayap di path final.
    lead = max(1, int(round(lead_sec / interval)))
    for i in range(1, n):
        if focus[i] is not None and focus[i - 1] is not None and focus[i] != focus[i - 1]:
            end_k = max(1, i - 2)
            start_k = max(0, end_k - lead)
            bx, by = list(tx), list(ty)
            for k in range(start_k, end_k + 1):
                r = (k - start_k) / max(1, end_k - start_k)
                w = r * r * (3 - 2 * r)  # smoothstep ease-in-out
                tx[k] = bx[k] * (1 - w) + _center_at(tracks[focus[i]], k) * w
                ty[k] = by[k] * (1 - w) + _cy_at(tracks[focus[i]], k) * w
            for k in range(end_k + 1, i):  # jaga lag deteksi: ikut pembicara baru
                tx[k] = _center_at(tracks[focus[i]], k)
                ty[k] = _cy_at(tracks[focus[i]], k)
    return times, tx, ty


def _smooth(xs: list, alpha=0.55) -> list:
    """EMA maju-mundur (zero-phase): halus tanpa jeda/geser fase.
    alpha 0.55: cukup meredam jitter deteksi. Kehalusan antar-sampel (C1)
    sudah dijamin interpolasi KUBIK Catmull-Rom (cutter._x_expr), jadi EMA
    TIDAK perlu berat — EMA berat memakan timing look-ahead (kamera telat
    sampai ke pembicara baru)."""
    y = xs[0]
    out = []
    for x in xs:
        y += alpha * (x - y)
        out.append(y)
    y = out[-1]
    for i in range(len(out) - 1, -1, -1):
        y += alpha * (out[i] - y)
        out[i] = y
    return out


def _clamp_speed(times, xs, src_w) -> list:
    """Batasi kecepatan pan (px/detik) — tidak ada teleport/overshoot."""
    vmax = src_w * 0.45
    out = [xs[0]]
    for i in range(1, len(xs)):
        dt = max(times[i] - times[i - 1], 1e-6)
        max_step = vmax * dt
        d = xs[i] - out[-1]
        if abs(d) > max_step:
            d = max_step if d > 0 else -max_step
        out.append(out[-1] + d)
    return out


def _keyframes(times, xs, src_w, crop_w) -> list:
    """Jadikan path -> keyframe: diam diringkas, gerak disimpan penuh (kecepatan kontinu)."""
    lo, hi = crop_w / 2, src_w - crop_w / 2
    xs = [min(max(x, lo), hi) for x in xs]
    tol = max(0.75, src_w * 0.002)
    kf = []
    moving = False
    for i in range(1, len(xs)):
        if abs(xs[i] - xs[i - 1]) > tol:
            if not moving:
                kf.append((times[i - 1], xs[i - 1]))
                moving = True
            kf.append((times[i], xs[i]))
        else:
            if moving:
                kf.append((times[i], xs[i]))
                moving = False
    if not kf:
        kf = [(times[0], xs[0])]
    if kf[0][0] > times[0] + 1e-6:
        kf.insert(0, (times[0], xs[0]))
    if kf[-1][0] < times[-1] - 1e-6:
        kf.append((times[-1], xs[-1]))
    return kf


def track(video_path, times: list, src_w: int, crop_w: int, t0: float = 0.0):
    """
    Satu pintu face tracking: sampel -> track -> fokus -> path mulus.
    -> (keyframes [(t, center_x_px)], focus_y [(t, cy_frac)], vision dict)
    keyframes kosong = tidak ada wajah -> cutter pakai crop tengah.
    vision = profil saliency + teks-bawaan + bbox wajah untuk smart placement.
    """
    samples = sample_faces(video_path, times)
    vision = _vision_summary(samples)
    if not samples or not any(s["faces"] for s in samples):
        return [], [], vision
    tracks = _build_tracks(samples, src_w)
    if not tracks:
        return [], [], vision  # (bug lama: 2 nilai -> ValueError saat unpack)
    for tr in tracks:
        _speaking_score(tr)
    focus = _focus_timeline(tracks, len(samples))
    t2, tx, ty = _focus_path(samples, tracks, focus, config.LEAD_AHEAD_SEC,
                             config.FACE_SAMPLE_INTERVAL)
    tx = _clamp_speed(t2, _smooth(tx), src_w)
    # CATATAN: cukup satu pass _smooth — kecepatan kontinu (C1) di tiap knot
    # sudah dijamin interpolasi KUBIK Catmull-Rom di cutter._x_expr.
    keyframes = _keyframes(t2, tx, src_w, crop_w)
    # WAJIB: ffmpeg -ss me-reset t ke 0 (waktu LOKAL klip) -> keyframe ikut digeser.
    # t0 = detik awal klip pada sumber (mode absolut). Mode segmen lokal: t0=0.
    keyframes = [(t - t0, x) for t, x in keyframes]
    return keyframes, list(zip(t2, ty)), vision
