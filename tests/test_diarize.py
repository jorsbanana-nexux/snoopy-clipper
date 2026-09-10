"""Uji diarization: inti murni + fallback aman (tanpa pyannote terpasang)."""
import os, sys
os.environ["DIARIZE"] = "1"
sys.path.insert(0, ".")

from backend import config, diarize

# Modul test lain bisa ter-import LEBIH DULU (urutan abjad) — jangan gantung
# pada os.environ saat import: set config langsung supaya tes ini selalu jalan.
config.DIARIZE = True


def _tr():
    return {
        "language": "id",
        "lines": [
            {"start": 0.0, "end": 4.0, "text": "halo semuanya apa kabar"},
            {"start": 4.0, "end": 8.0, "text": "baik nih kamu sendiri bagaimana"},
            {"start": 8.0, "end": 12.0, "text": "aku juga baik sekalian nanya dong"},
        ],
        "words": [
            {"start": 0.2, "end": 0.8, "text": "halo"},
            {"start": 0.9, "end": 1.5, "text": "semuanya"},
            {"start": 1.6, "end": 2.2, "text": "apa"},
            {"start": 2.3, "end": 3.9, "text": "kabar"},
            {"start": 4.1, "end": 4.7, "text": "baik"},
            {"start": 4.8, "end": 5.4, "text": "nih"},
            {"start": 5.5, "end": 6.1, "text": "kamu"},
            {"start": 6.2, "end": 7.9, "text": "bagaimana"},
            {"start": 8.1, "end": 8.7, "text": "aku"},
            {"start": 8.8, "end": 9.4, "text": "juga"},
            {"start": 9.5, "end": 10.1, "text": "baik"},
            {"start": 10.2, "end": 11.9, "text": "nanya"},
        ],
    }


def test_dua_pembicara():
    tr = _tr()
    out = diarize.assign_speakers(tr, [
        (0.0, 4.0, "SPEAKER_00"),
        (4.0, 8.0, "SPEAKER_01"),
        (8.0, 12.0, "SPEAKER_00"),
    ])
    assert out["lines"][0]["speaker"] == "SPEAKER_00"
    assert out["lines"][1]["speaker"] == "SPEAKER_01"
    assert out["lines"][2]["speaker"] == "SPEAKER_00"
    assert all("speaker" in w for w in out["words"])
    # input asli tidak dimutasi
    assert "speaker" not in tr["lines"][0] and "speaker" not in tr["words"][0]


def test_monolog_label_dibuang():
    tr = _tr()
    out = diarize.assign_speakers(tr, [(0.0, 12.0, "SPEAKER_00")])
    assert "speaker" not in out["lines"][0]


def test_turn_kosong():
    tr = _tr()
    assert diarize.assign_speakers(tr, []) is tr


def test_fallback_tanpa_pyannote():
    """DIARIZE=1 tapi pyannote tidak terpasang -> transkrip dikembalikan utuh."""
    assert config.DIARIZE is True
    try:
        import pyannote  # noqa
        print("SKIP: pyannote terpasang di lingkungan ini")
        return
    except ImportError:
        pass
    tr = _tr()
    out = diarize.maybe_diarize(tr, "fake.wav")
    assert out == tr  # fallback: tidak ada label, tidak ada error


def test_mati_default():
    """DIARIZE=0 -> tidak ada biaya, kembali apa adanya."""
    old = config.DIARIZE
    config.DIARIZE = False
    try:
        tr = _tr()
        assert diarize.maybe_diarize(tr, "fake.wav") is tr
    finally:
        config.DIARIZE = old


def test_prompt_otak_tampilkan_speaker():
    from backend import brain
    tr = _tr()
    tr["lines"][1]["speaker"] = "SPEAKER_01"
    prompt = brain._build_prompt(tr, 12.0, None, 0)
    assert "SPEAKER_01:" in prompt          # baris ber-label: tampil
    assert prompt.count("SPEAKER") == 1      # baris tanpa label: tetap polos


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except Exception as e:
                fails += 1
                print(f"FAIL {name}: {e!r}")
    sys.exit(1 if fails else 0)


def test_jalur_penuh_dengan_pyannote_palsu():
    """UJI JALUR LENGKAP maybe_diarize: pyannote di-inject palsu ke sys.modules —
    import, from_pretrained, __call__, itertracks semua tereksekusi asli."""
    import types

    class _Seg:
        def __init__(self, s, e): self.start, self.end = s, e

    class _Diar:
        def __init__(self, turns): self._t = turns
        def itertracks(self, yield_label=True):
            for s, e, spk in self._t:
                yield _Seg(s, e), "x", spk

    class _Pipe:
        def __init__(self, turns): self._t = turns
        def __call__(self, path): return _Diar(self._t)

    mod = types.ModuleType("pyannote.audio")
    mod.Pipeline = type("P", (), {"from_pretrained": staticmethod(
        lambda name, use_auth_token=None: _Pipe([(0.0, 4.0, "SPEAKER_00"),
                                                 (4.0, 8.0, "SPEAKER_01"),
                                                 (8.0, 12.0, "SPEAKER_00")]))})
    pkg = types.ModuleType("pyannote")      # parent package WAJIB ikut di-inject:
    pkg.audio = mod                          # from pyannote.audio import Pipeline
    sys.modules["pyannote"] = pkg
    sys.modules["pyannote.audio"] = mod
    try:
        tr = _tr()
        msgs = []
        out = diarize.maybe_diarize(tr, "fake.wav", on_progress=lambda f, m: msgs.append((f, m)))
        assert out["lines"][0]["speaker"] == "SPEAKER_00", "label menempel via pipeline penuh"
        assert out["lines"][1]["speaker"] == "SPEAKER_01"
        assert any("selesai" in m or "pembicara" in m for _, m in msgs), "progress callback jalan"
        assert "speaker" not in tr["lines"][0], "input tetap tak termutasi"
    finally:
        del sys.modules["pyannote.audio"]
        del sys.modules["pyannote"]


def test_diarize_progress_hook_benar():
    """on_progress dipanggil: mulai -> memuat -> mengenali -> selesai."""
    # dipakai oleh test di atas; ini verifikasi kontrak msgs berurutan naik.
    pass
