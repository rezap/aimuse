import io

import pytest
import soundfile as sf

from aimuse.engines import EngineError, FakeEngine
from muse_jobs import JobRequest, display_bpm, friendly_engine_error, process_job


class MemoryStore:
    def __init__(self, jobs: dict):
        self.jobs = jobs  # job_id -> data
        self.tracks: dict = {}
        self.spend: dict = {}
        self.influences: dict = {}

    def claim_job(self, uid, job_id):
        job = self.jobs.get(job_id)
        if not job or job.get("status") != "queued":
            return None
        job["status"] = "running"
        return dict(job)

    def reserve_spend(self, uid, day, usd, cap_usd):
        day_spend = self.spend.get((uid, day), 0.0)
        if day_spend + usd > cap_usd + 1e-9:
            return False
        self.spend[(uid, day)] = day_spend + usd
        return True

    def complete_job(self, uid, job_id, track):
        self.tracks[job_id] = track
        self.jobs[job_id].update(status="done", trackId=job_id)

    def get_influence(self, key):
        return self.influences.get(key)

    def save_influence(self, key, reference, traits):
        self.influences[key] = traits

    def fail_job(self, uid, job_id, message):
        self.jobs[job_id].update(status="failed", error=message)


class MemoryAudio:
    def __init__(self):
        self.files = {}

    def upload(self, path, data, content_type):
        self.files[path] = (data, content_type)


def _run(store, audio, engine=None, cap=1.0, job_id="j1", allowed=True, translator=None):
    return process_job(
        "u1",
        job_id,
        store=store,
        audio=audio,
        engine_factory=lambda: engine or FakeEngine(max_seconds=10, cost_usd=0.08),
        daily_cap_usd=cap,
        is_allowed=lambda uid: allowed,
        translator_factory=(lambda: translator) if translator else None,
    )


def _job(**kw):
    return {"status": "queued", "stationId": "rainy-morning-indie", **kw}


def test_happy_path_uploads_audio_and_writes_track():
    store = MemoryStore({"j1": _job(theme="first snow", mood="cosy", energy=0.3)})
    audio = MemoryAudio()
    assert _run(store, audio) == "done"
    assert store.jobs["j1"]["status"] == "done"
    ((path, (data, mime)),) = audio.files.items()
    assert path == "users/u1/tracks/j1.wav" and mime == "audio/wav"
    y, sr = sf.read(io.BytesIO(data))
    assert len(y) / sr == pytest.approx(10, abs=0.1)
    t = store.tracks["j1"]
    assert t["title"] == "First snow" and t["stationName"] == "Rainy Morning Indie"
    assert t["audioPath"] == path and t["rating"] == 0 and t["vocals"] is True
    assert t["bpm"] and t["key"] and "first snow" in t["prompt"]
    assert t["costUsd"] == 0.08


def test_duplicate_delivery_is_skipped():
    store, audio = MemoryStore({"j1": _job()}), MemoryAudio()
    assert _run(store, audio) == "done"
    assert _run(store, audio) == "skipped"
    assert len(audio.files) == 1


def test_daily_cap_blocks_without_calling_engine():
    engine = FakeEngine(max_seconds=10, cost_usd=0.08)
    store = MemoryStore({"j1": _job(), "j2": _job()})
    audio = MemoryAudio()
    assert _run(store, audio, engine, cap=0.10, job_id="j1") == "done"
    assert _run(store, audio, engine, cap=0.10, job_id="j2") == "failed"
    assert "Daily limit" in store.jobs["j2"]["error"]
    assert engine.calls == 1


def test_bad_requests_fail_cleanly():
    store = MemoryStore(
        {
            "a": _job(stationId="nope"),
            "b": _job(energy=7),
            "c": _job(theme="x" * 500),
        }
    )
    for job_id in "abc":
        assert _run(store, MemoryAudio(), job_id=job_id) == "failed"
    assert "Unknown station" in store.jobs["a"]["error"]
    assert store.jobs["b"]["error"].startswith("Invalid request")
    assert store.jobs["c"]["error"].startswith("Invalid request")


def test_engine_error_marks_job_failed():
    class Blocked(FakeEngine):
        def generate(self, prompt):
            raise EngineError("Lyria returned no audio: blocked")

    store = MemoryStore({"j1": _job()})
    assert _run(store, MemoryAudio(), Blocked(cost_usd=0.08)) == "failed"
    assert "blocked" in store.jobs["j1"]["error"]


def test_unexpected_error_fails_job_then_raises():
    class Broken(FakeEngine):
        def generate(self, prompt):
            raise RuntimeError("boom")

    store = MemoryStore({"j1": _job()})
    with pytest.raises(RuntimeError):
        _run(store, MemoryAudio(), Broken())
    assert store.jobs["j1"]["status"] == "failed"
    assert "RuntimeError" in store.jobs["j1"]["error"]


def test_request_to_intent():
    data = {"stationId": "s", "vocals": False, "theme": "  ", "mood": "calm"}
    r = JobRequest.model_validate(data)
    i = r.to_intent()
    assert i.vocals.value == "instrumental" and i.theme is None and i.label == "calm"


def test_display_bpm_folds_half_and_double_time():
    assert display_bpm(152.0, 78) == 76.0
    assert display_bpm(44.0, 90) == 88.0
    assert display_bpm(100.0, 100) == 100.0
    assert display_bpm(None, 90) is None


def test_not_invited_user_is_refused_before_any_spend():
    engine = FakeEngine(max_seconds=10, cost_usd=0.08)
    store = MemoryStore({"j1": _job()})
    assert _run(store, MemoryAudio(), engine, allowed=False) == "failed"
    assert "invite-only" in store.jobs["j1"]["error"]
    assert engine.calls == 0 and store.spend == {}


def test_artist_inspiration_becomes_traits_never_the_name():
    from aimuse.inspiration import FakeStyleTranslator, mentions_reference

    translator = FakeStyleTranslator()
    store = MemoryStore(
        {"j1": _job(inspiration="Bob Dylan", vocals=True), "j2": _job(inspiration="bob  DYLAN")}
    )
    assert _run(store, MemoryAudio(), translator=translator, job_id="j1") == "done"
    assert _run(store, MemoryAudio(), translator=translator, job_id="j2") == "done"
    t = store.tracks["j1"]
    assert t["inspiration"] == "Bob Dylan" and t["inspirationNote"] is None
    assert t["influences"].startswith("folk rock")
    assert "harmonica" in t["prompt"] and not mentions_reference(t["prompt"], "Bob Dylan")
    # Translated once, then reused for the same artist (any spelling/case).
    assert translator.calls == 1 and list(store.influences) == ["bob-dylan"]


def test_failed_translation_still_makes_the_song():
    from aimuse.inspiration import FakeStyleTranslator, InspirationError

    class Broken(FakeStyleTranslator):
        def translate(self, reference):
            raise InspirationError("couldn't recognise that as a musical style")

    store = MemoryStore({"j1": _job(inspiration="my cat"), "j2": _job(inspiration="x")})
    assert _run(store, MemoryAudio(), translator=Broken(), job_id="j1") == "done"
    assert "couldn't recognise" in store.tracks["j1"]["inspirationNote"]
    assert store.tracks["j1"]["influences"] is None
    assert _run(store, MemoryAudio(), job_id="j2") == "done"  # no translator configured
    assert "not enabled" in store.tracks["j2"]["inspirationNote"]


def test_inspiration_too_long_is_rejected():
    store = MemoryStore({"j1": _job(inspiration="x" * 81)})
    assert _run(store, MemoryAudio()) == "failed"
    assert store.jobs["j1"]["error"].startswith("Invalid request")


def test_own_lyrics_job():
    lyrics = "If you can keep your head when all about you\n    Are losing theirs\n"
    store = MemoryStore({"j1": _job(lyrics=lyrics, vocals=False)})
    assert _run(store, MemoryAudio()) == "done"
    t = store.tracks["j1"]
    assert t["ownLyrics"] is True and t["vocals"] is True  # lyrics are always sung
    assert t["title"] == "If you can keep your head when all about you"
    assert "Lyrics:\n[Verse 1]\nIf you can keep your head" in t["prompt"]


def test_lyrics_too_long_rejected():
    store = MemoryStore({"j1": _job(lyrics="la " * 1001)})
    assert _run(store, MemoryAudio()) == "failed"
    assert store.jobs["j1"]["error"].startswith("Invalid request")


def test_refusals_are_explained():
    msg = friendly_engine_error(
        "Lyria API error 400: Request blocked by safety filters (recitation)"
    )
    assert msg.startswith("Lyria declined to make this song") and "recitation" in msg
    assert friendly_engine_error("Lyria API error 500: boom") == "Lyria API error 500: boom"

    class Refusing(FakeEngine):
        def generate(self, prompt):
            raise EngineError("Lyria returned no audio: blocked")

    store = MemoryStore({"j1": _job(lyrics="some famous words")})
    assert _run(store, MemoryAudio(), Refusing(cost_usd=0.08)) == "failed"
    assert store.jobs["j1"]["error"].startswith("Lyria declined to make this song")
