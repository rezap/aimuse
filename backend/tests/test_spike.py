import json

import pytest

from aimuse.cli import main
from aimuse.engines import EngineError, FakeEngine
from aimuse.spike import run_spike


def test_spike_end_to_end(tmp_path, style):
    report = run_spike(
        FakeEngine(max_seconds=10), style, tmp_path, tracks=2, candidates=2, normalize=True
    )
    assert report.requests == 8 and report.stopped_early is None
    for s in report.summaries:
        assert s.tracks == 2 and s.tracks_with_audio == 2 and s.failed_requests == 0
        assert s.qa_pass_rate == 1.0 and s.bpm_adherence == 1.0 and s.key_adherence == 1.0
        assert s.consistency is not None and s.consistency > 0.9
    data = json.loads((tmp_path / "report.json").read_text())
    assert data["summaries"][0]["arm"] == "text"
    assert "embedding" not in json.dumps(data)
    assert (tmp_path / "anchor.png").exists()
    md = (tmp_path / "report.md").read_text()
    assert "| text | 2 | 2 | 0 | 100% |" in md
    for t in report.tracks:
        chosen = t.chosen_candidate
        assert chosen is not None and (tmp_path / chosen.file).exists()
        assert (tmp_path / t.normalized_file).exists()
        recipe = json.loads((tmp_path / "tracks" / t.arm / f"{t.name}.recipe.json").read_text())
        assert recipe["style"]["id"] == "test-station" and recipe["prompt_text"]
        assert "license_note" in recipe


def test_budget_cap_stops_before_overspending(tmp_path, style):
    engine = FakeEngine(max_seconds=10, cost_usd=0.4)
    report = run_spike(engine, style, tmp_path, tracks=3, candidates=1, max_cost_usd=1.0)
    assert engine.calls == 2 and report.requests == 2
    assert report.spent_usd == pytest.approx(0.8)
    assert "exceed the $1.00 cap" in report.stopped_early


def test_engine_errors_are_recorded_not_fatal(tmp_path, style):
    class Flaky(FakeEngine):
        def generate(self, prompt):
            if self.calls == 0:
                self.calls += 1
                raise EngineError("blocked by safety filter")
            return super().generate(prompt)

    report = run_spike(Flaky(max_seconds=10), style, tmp_path, tracks=1, arms=["text", "image"])
    text = report.summaries[0]
    assert text.failed_requests == 1 and text.tracks_with_audio == 0
    assert "blocked by safety filter" in (tmp_path / "report.md").read_text()


def test_unknown_arm_rejected(tmp_path, style):
    with pytest.raises(ValueError):
        run_spike(FakeEngine(), style, tmp_path, arms=["video"])


def test_cli_prompt_presets_and_fake_spike(tmp_path, capsys):
    assert main(["presets"]) == 0
    assert "late-night-lofi" in capsys.readouterr().out
    assert main(["prompt", "--preset", "late-night-lofi"]) == 0
    assert "Instrumental only, no vocals." in capsys.readouterr().out
    out = tmp_path / "run"
    code = main(
        [
            "spike",
            "--engine",
            "fake",
            "--preset",
            "late-night-lofi",
            "--tracks",
            "1",
            "--arms",
            "text",
            "--out",
            str(out),
        ]
    )
    assert code == 0 and (out / "report.md").exists()


def test_cli_lyria_requires_key(tmp_path, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(ValueError, match="GEMINI_API_KEY"):
        main(["spike", "--engine", "lyria", "--tracks", "1", "--out", str(tmp_path)])


def test_missing_vocals_are_flagged_and_ranked_lower(tmp_path, style):
    from aimuse.models import Intent
    from aimuse.pipeline import Budget, generate_track, rank

    class SometimesInstrumental(FakeEngine):
        def generate(self, prompt):
            asset = super().generate(prompt)
            if self.calls == 1:
                asset.lyrics = "<instrumental>"
            return asset

    track = generate_track(
        SometimesInstrumental(max_seconds=10),
        style,
        Intent(theme="x"),
        name="t",
        arm="a",
        out_dir=tmp_path,
        budget=Budget(1.0),
        candidates=2,
    )
    rank([track])
    first, second = track.candidates
    assert first.vocals_ok is False and second.vocals_ok is True
    assert any("instrumental" in i for i in first.qa.issues)
    assert track.chosen == 1
