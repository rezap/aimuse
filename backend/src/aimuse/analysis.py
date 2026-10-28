"""Audio analysis: decode, measure, check against targets, and embed for consistency."""

from __future__ import annotations

import io
import subprocess

import librosa
import numpy as np
import pyloudnorm
import soundfile as sf
from pydantic import BaseModel

from .models import PITCH_CLASSES, Key, TargetSpec

ANALYSIS_SR = 22050

# Krumhansl-Kessler key profiles.
_MAJOR = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
_MINOR = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])


class TrackAnalysis(BaseModel):
    duration_s: float
    sample_rate: int
    channels: int
    bpm: float
    key: str
    key_confidence: float
    lufs: float
    peak_dbfs: float
    clipping_ratio: float
    silence_ratio: float
    spectral_centroid_hz: float
    embedding: list[float]  # timbre/harmony features, used for ranking (typicality)
    spectrum_db: list[float]  # mean log-mel spectral shape, used for consistency


class QAResult(BaseModel):
    passed: bool
    bpm_ok: bool
    key_ok: bool | None  # None when no key was requested
    duration_ok: bool
    issues: list[str]


def decode(data: bytes) -> tuple[np.ndarray, int]:
    """Decode audio bytes to float32 (frames, channels). Falls back to ffmpeg."""
    try:
        y, sr = sf.read(io.BytesIO(data), dtype="float32", always_2d=True)
        return y, sr
    except (sf.LibsndfileError, RuntimeError):
        proc = subprocess.run(
            ["ffmpeg", "-loglevel", "error", "-i", "pipe:0", "-f", "wav", "pipe:1"],
            input=data,
            capture_output=True,
            check=True,
        )
        y, sr = sf.read(io.BytesIO(proc.stdout), dtype="float32", always_2d=True)
        return y, sr


def detect_key(chroma_mean: np.ndarray) -> tuple[Key, float]:
    best, best_r, scores = None, -2.0, []
    for mode, profile in (("major", _MAJOR), ("minor", _MINOR)):
        for tonic in range(12):
            r = float(np.corrcoef(chroma_mean, np.roll(profile, tonic))[0, 1])
            scores.append(r)
            if r > best_r:
                best, best_r = Key(tonic=PITCH_CLASSES[tonic], mode=mode), r
    scores.sort(reverse=True)
    confidence = max(0.0, scores[0] - scores[1])
    return best, confidence


def analyze(y: np.ndarray, sr: int) -> TrackAnalysis:
    mono = y.mean(axis=1) if y.ndim == 2 else y
    duration = len(mono) / sr
    peak = float(np.max(np.abs(y))) if y.size else 0.0
    clipping = float(np.mean(np.abs(y) >= 0.999)) if y.size else 0.0

    meter = pyloudnorm.Meter(sr)
    try:
        lufs = float(meter.integrated_loudness(y if y.ndim == 2 else mono[:, None]))
    except ValueError:  # shorter than one gating block
        lufs = float("-inf")

    m = librosa.resample(mono, orig_sr=sr, target_sr=ANALYSIS_SR) if sr != ANALYSIS_SR else mono
    rms = librosa.feature.rms(y=m)[0]
    silence = float(np.mean(rms < 10 ** (-60 / 20)))

    onset_env = librosa.onset.onset_strength(y=m, sr=ANALYSIS_SR)
    tempo = librosa.feature.tempo(onset_envelope=onset_env, sr=ANALYSIS_SR)
    bpm = float(np.atleast_1d(tempo)[0])

    chroma = librosa.feature.chroma_stft(y=m, sr=ANALYSIS_SR)
    chroma_mean = chroma.mean(axis=1)
    key, key_conf = detect_key(chroma_mean)

    mfcc = librosa.feature.mfcc(y=m, sr=ANALYSIS_SR, n_mfcc=20)
    contrast = librosa.feature.spectral_contrast(y=m, sr=ANALYSIS_SR)
    centroid = librosa.feature.spectral_centroid(y=m, sr=ANALYSIS_SR)[0]
    mel_db = librosa.power_to_db(librosa.feature.melspectrogram(y=m, sr=ANALYSIS_SR, n_mels=64))
    spectrum = mel_db.mean(axis=1)
    embedding = np.concatenate(
        [mfcc.mean(axis=1), mfcc.std(axis=1), chroma_mean, contrast.mean(axis=1)]
    )

    return TrackAnalysis(
        duration_s=round(duration, 2),
        sample_rate=sr,
        channels=y.shape[1] if y.ndim == 2 else 1,
        bpm=round(bpm, 1),
        key=str(key),
        key_confidence=round(key_conf, 3),
        lufs=round(lufs, 2) if np.isfinite(lufs) else -99.0,
        peak_dbfs=round(20 * np.log10(max(peak, 1e-9)), 2),
        clipping_ratio=round(clipping, 5),
        silence_ratio=round(silence, 4),
        spectral_centroid_hz=round(float(centroid.mean()), 1),
        embedding=[float(v) for v in embedding],
        spectrum_db=[round(float(v), 3) for v in spectrum],
    )


def bpm_matches(measured: float, target: float, tolerance: float = 0.04) -> bool:
    """True if measured tempo is within tolerance of target, allowing half/double time."""
    return any(abs(measured * f - target) <= tolerance * target for f in (1.0, 0.5, 2.0))


def key_matches(measured: str, target: str) -> bool:
    """Same key or its relative major/minor (same notes, often confused by detectors)."""
    m, t = Key.parse(measured), Key.parse(target)
    return m == t or m == t.relative()


def check(analysis: TrackAnalysis, target: TargetSpec, *, min_duration_ratio=0.6) -> QAResult:
    issues = []
    bpm_ok = bpm_matches(analysis.bpm, target.bpm)
    if not bpm_ok:
        issues.append(f"tempo {analysis.bpm} BPM, wanted {target.bpm}")
    key_ok = None
    if target.key:
        key_ok = key_matches(analysis.key, target.key)
        if not key_ok:
            issues.append(f"key {analysis.key}, wanted {target.key}")
    duration_ok = analysis.duration_s >= min_duration_ratio * target.duration_s
    if not duration_ok:
        issues.append(f"duration {analysis.duration_s}s, wanted ~{target.duration_s}s")
    if analysis.clipping_ratio > 0.001:
        issues.append(f"clipping on {analysis.clipping_ratio:.2%} of samples")
    if analysis.silence_ratio > 0.2:
        issues.append(f"{analysis.silence_ratio:.0%} silence")
    # Tempo/key misses are reported but don't fail QA on their own: they're scored in ranking.
    hard_fail = (not duration_ok) or analysis.clipping_ratio > 0.001 or analysis.silence_ratio > 0.2
    return QAResult(
        passed=not hard_fail, bpm_ok=bpm_ok, key_ok=key_ok, duration_ok=duration_ok, issues=issues
    )


def normalize_loudness(
    y: np.ndarray, sr: int, target_lufs: float = -14.0, peak_ceiling_dbfs: float = -1.0
) -> tuple[np.ndarray, float]:
    """Gain-normalise to target integrated loudness without exceeding the peak ceiling."""
    loudness = pyloudnorm.Meter(sr).integrated_loudness(y)
    gain_db = target_lufs - loudness
    peak = float(np.max(np.abs(y)))
    if peak > 0:
        max_gain_db = peak_ceiling_dbfs - 20 * np.log10(peak)
        gain_db = min(gain_db, max_gain_db)
    return (y * 10 ** (gain_db / 20)).astype(np.float32), round(float(gain_db), 2)


def consistency(spectra: list[list[float]]) -> float:
    """Mean pairwise correlation of the tracks' average spectral shapes, in [-1, 1].

    Independent of the rest of the run, so numbers are comparable across runs: identical
    sounding tracks score ~1, unrelated styles much lower.
    """
    if len(spectra) < 2:
        return float("nan")
    s = np.array(spectra)
    s = s - s.mean(axis=1, keepdims=True)
    s /= np.linalg.norm(s, axis=1, keepdims=True) + 1e-9
    sims = s @ s.T
    iu = np.triu_indices(len(s), k=1)
    return round(float(sims[iu].mean()), 4)


def typicality(embedding: list[float], reference: list[list[float]]) -> float:
    """How close a track sits to the centre of a reference set, in (0, 1]; 1 = dead centre.

    Features are z-scored over the reference set, so the centre is the origin and the score is
    1 / (1 + RMS z-distance). Used to keep the candidate that best matches the station's sound.
    """
    ref = np.array(reference)
    if len(ref) < 2:
        return 1.0
    mu, sd = ref.mean(axis=0), ref.std(axis=0) + 1e-9
    z = (np.array(embedding) - mu) / sd
    return round(float(1.0 / (1.0 + np.sqrt(np.mean(z**2)))), 4)
