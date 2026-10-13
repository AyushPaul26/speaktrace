"""Signal fixtures are independent tones; no augmentation labels reach the core."""
import importlib
import json

import numpy as np
import pytest


SR = 16000


def extract(audio, sample_rate=SR):
    return importlib.import_module("speaktrace.core.features").extract_features(audio, sample_rate)


def tone(hz=200, seconds=2, amplitude=.2):
    t = np.arange(round(seconds * SR)) / SR
    return amplitude * np.sin(2 * np.pi * hz * t)


def test_tone_features_are_finite_compact_and_measured():
    result = extract(tone())
    json.dumps(result, allow_nan=False)
    assert set(result) == {"times", "rms_db", "pitch_st", "spectral_centroid", "mfcc_summary", "waveform", "voiced_fraction"}
    assert 10 < len(result["times"]) <= 1200
    assert len(result["times"]) == len(result["rms_db"]) == len(result["pitch_st"]) == len(result["spectral_centroid"])
    assert len(result["mfcc_summary"]) == 13
    assert len(result["waveform"]) <= 600
    assert result["voiced_fraction"] > .9
    assert np.median(result["spectral_centroid"]) == pytest.approx(200, abs=5)
    assert np.median(result["rms_db"]) == pytest.approx(0, abs=.1)
    assert np.median([p for p in result["pitch_st"] if p is not None]) == pytest.approx(0, abs=.1)
    assert min(bin["min"] for bin in result["waveform"]) == pytest.approx(-.2, abs=.002)
    assert max(bin["max"] for bin in result["waveform"]) == pytest.approx(.2, abs=.002)


def test_pitch_is_relative_semitones_not_hertz():
    result = extract(np.concatenate([tone(150), tone(300)]))
    low = [p for t, p in zip(result["times"], result["pitch_st"]) if .2 < t < 1.8 and p is not None]
    high = [p for t, p in zip(result["times"], result["pitch_st"]) if 2.2 < t < 3.8 and p is not None]
    assert np.median(high) - np.median(low) == pytest.approx(12, abs=.6)


def test_relative_features_ignore_constant_gain():
    audio = np.concatenate([tone(amplitude=.15), tone(amplitude=.3)])
    original, quieter = extract(audio), extract(audio * .07)
    assert quieter["rms_db"] == pytest.approx(original["rms_db"], abs=1e-6)
    assert quieter["pitch_st"] == pytest.approx(original["pitch_st"], abs=1e-6)
    assert quieter["spectral_centroid"] == pytest.approx(original["spectral_centroid"], abs=1e-5)


def test_silence_and_tiny_nonempty_clips_are_json_safe():
    for audio in [np.zeros(SR), np.array([.2])]:
        result = extract(audio)
        json.dumps(result, allow_nan=False)
        assert len(result["times"]) >= 1
    silent = extract(np.zeros(SR))
    assert silent["voiced_fraction"] == 0
    assert all(p is None for p in silent["pitch_st"])


@pytest.mark.parametrize("audio,sr", [(np.array([]), SR), (np.array([np.nan]), SR), (np.array([np.inf]), SR), (np.ones((2, 100)), SR), (tone(), 0), (tone(), 16000.5)])
def test_invalid_audio_fails_cleanly(audio, sr):
    with pytest.raises(ValueError):
        extract(audio, sr)


def test_long_clip_feature_payload_stays_bounded_without_losing_end_of_timeline():
    result = extract(tone(seconds=60))
    assert len(result["times"]) <= 1200
    assert len(result["waveform"]) <= 600
    assert result["times"][0] == 0
    assert result["times"][-1] == pytest.approx(60, abs=.03)
    json.dumps(result, allow_nan=False)
