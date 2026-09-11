"""PERISAI BADAI 503: model TERTINGGI harus diberi waktu pulih dulu
(backoff eksponensial 2s->4s->8s...), bukan langsung jatuh ke model bawah.
Kuota (429) / model mati (404) tetap lompat SEGERA — mengulang dijamin
sia-sia. Terbukti hidup 2026-09-11: badai 503 'high demand' bikin klip
turun ke model bawah padahal quota kunci masih ada."""


class _Err(Exception):
    pass


class _Resp:
    def __init__(self, model):
        self.text = '{"ok": "%s"}' % model


class _Models:
    def __init__(self, script):
        self.script = list(script)

    def generate_content(self, model, contents, config=None):
        step = self.script.pop(0)
        if isinstance(step, Exception):
            raise step
        return _resp_for(step)


def _resp_for(name):
    return _Resp(name)


class _FakeTypes:
    class GenerateContentConfig:
        def __init__(self, **kw):
            self.kw = kw


def _setup(monkeypatch, script):
    import backend.brain as b
    monkeypatch.setattr(b, "_model_attempts", lambda: ["top", "low"])
    sleeps = []
    b._sleeps = sleeps
    monkeypatch.setattr(b.time, "sleep", sleeps.append)
    client = type("C", (), {})()
    client.models = _Models(script)
    return b, client


def test_badai_503_diberi_waktu_pulih_turun_sebelum_model_tertinggi(monkeypatch):
    """503 dua kali lalu pulih -> model TERTINGGI tetap dipakai; jeda tumbuh 2s lalu 4s."""
    b, client = _setup(monkeypatch, [
        _Err("503 UNAVAILABLE high demand"),
        _Err("503 UNAVAILABLE high demand"),
        "top",
    ])
    resp = b._generate_with_fallback(client, _FakeTypes, ["p"])
    assert "top" in resp.text            # TIDAK turun ke model bawah
    assert b._sleeps == [2.0, 4.0]      # backoff eksponensial, bukan jeda tetap


def test_503_kebanjiran_retry_habis_turun_ke_cadangan(monkeypatch):
    """Retry habis (GEMINI_PRIMARY_RETRIES=3) -> tetap turun ke cadangan,
    klip tidak boleh mati; jeda antar ulang tumbuh eksponensial."""
    b, client = _setup(monkeypatch, [
        _Err("503 UNAVAILABLE"), _Err("503 UNAVAILABLE"), _Err("503 UNAVAILABLE"),
        "low",
    ])
    resp = b._generate_with_fallback(client, _FakeTypes, ["p"])
    assert "low" in resp.text
    assert b._sleeps == [2.0, 4.0, 2.0]
    # 2s+4s = backoff ulang model tertinggi; 2s terakhir = jeda napas
    # pindah model (perilaku asli yang disengaja, tetap dipertahankan)


def test_quota_429_lompat_segera_tanpa_jeda(monkeypatch):
    b, client = _setup(monkeypatch, [
        _Err("429 RESOURCE_EXHAUSTED quota exceeded"),
        "low",
    ])
    resp = b._generate_with_fallback(client, _FakeTypes, ["p"])
    assert "low" in resp.text
    assert b._sleeps == []               # kuota: mengulang = sia-sia


def test_model_mati_404_lompat_segera(monkeypatch):
    b, client = _setup(monkeypatch, [
        _Err("404 NOT_FOUND no longer available"),
        "low",
    ])
    resp = b._generate_with_fallback(client, _FakeTypes, ["p"])
    assert "low" in resp.text
    assert b._sleeps == []
