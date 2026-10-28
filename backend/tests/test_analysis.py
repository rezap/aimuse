import math

import numpy as np
import pyloudnorm

from aimuse.analysis import (
    analyze,
    bpm_matches,
    check,
    consistency,
    key_matches,
    normalize_loudness,
    typicality,
)
from aimuse.engines.fake import SR, synth_track
from aimuse.models import Key, TargetSpec, Vocals


def test_analyze_recovers_tempo_and_key():
    y = synth_track(100, Key.parse("A minor"), 10, seed=1)
    a = analyze(y, SR)
    assert bpm_matches(a.bpm, 100)
    assert key_matches(a.key, "A minor")
    assert abs(a.duration_s - 10) < 0.1 and a.channels == 2
    target = TargetSpec(bpm=100, key="A minor", duration_s=10, vocals=Vocals.VOCALS)
    qa = check(a, target)
    assert qa.passed and qa.bpm_ok and qa.key_ok and not qa.issues


def test_check_flags_short_and_off_key():
    a = analyze(synth_track(100, Key.parse("A minor"), 10, seed=1), SR)
    qa = check(a, TargetSpec(bpm=140, key="F# major", duration_s=60, vocals=Vocals.VOCALS))
    assert not qa.passed and not qa.bpm_ok and qa.key_ok is False and not qa.duration_ok
    assert len(qa.issues) == 3


def test_bpm_and_key_matching_rules():
    assert bpm_matches(60.5, 120) and bpm_matches(241, 120) and not bpm_matches(110, 120)
    assert key_matches("C major", "A minor") and not key_matches("D major", "A minor")


def test_consistency_and_typicality():
    s1 = list(np.linspace(-10, -60, 64))
    s2 = list(np.linspace(-60, -10, 64))
    assert consistency([s1, s1, s1]) == 1.0
    assert consistency([s1, s2]) < 0
    assert math.isnan(consistency([s1]))
    ref = [[0.0, 0.0], [1.0, 1.0], [2.0, 2.0]]
    assert typicality([1.0, 1.0], ref) > typicality([2.0, 2.0], ref)


def test_normalize_loudness_hits_target_under_ceiling():
    y = synth_track(100, Key.parse("C major"), 6, seed=2) * 0.1
    out, gain = normalize_loudness(y, SR, target_lufs=-16.0, peak_ceiling_dbfs=-1.0)
    assert gain > 0
    assert 20 * np.log10(np.max(np.abs(out))) <= -1.0 + 1e-3
    loud = pyloudnorm.Meter(SR).integrated_loudness(out)
    assert loud <= -16.0 + 0.5
