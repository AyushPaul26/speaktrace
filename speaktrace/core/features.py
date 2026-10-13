"""Small CPU-only signal diagnostics, with no models, labels, or network access.

Pitch is an autocorrelation estimate, not a clinical measure. Centroid and MFCCs
describe timbre and recording conditions; neither enters delivery scoring.
"""
from numbers import Integral

import numpy as np
from scipy.fft import dct, irfft, next_fast_len, rfft, rfftfreq
from scipy.signal import find_peaks


def validate_audio(audio: np.ndarray, sample_rate: int) -> np.ndarray:
    """Validate before arithmetic, avoiding silent NaN propagation and stereo bugs."""
    if isinstance(sample_rate, bool) or not isinstance(sample_rate, Integral) or not 1000 <= sample_rate <= 192000:
        raise ValueError("Sample rate must be an integer between 1000 and 192000 Hz.")
    try:
        original = np.asarray(audio)
        if np.iscomplexobj(original):
            raise ValueError("Audio must contain real samples.")
        samples = np.asarray(original, dtype=np.float64)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError("Audio must be a finite mono waveform.") from error
    if samples.ndim != 1 or samples.size == 0 or not np.all(np.isfinite(samples)):
        raise ValueError("Audio must be a nonempty finite mono waveform.")
    return samples


def _pitch(frames: np.ndarray, sample_rate: int, active: np.ndarray) -> np.ndarray:
    """Normalized autocorrelation with 70–400 Hz search and a periodicity gate."""
    width = frames.shape[1]
    fft_size = next_fast_len(2 * width - 1)
    correlation = irfft(np.abs(rfft(frames, n=fft_size)) ** 2, n=fft_size)[:, :width]
    cumulative = np.pad(np.cumsum(frames * frames, axis=1), ((0, 0), (1, 0)))
    low, high = max(2, int(sample_rate / 400)), min(width - 2, int(sample_rate / 70))
    result = np.full(len(frames), np.nan)
    lags = np.arange(low, high + 1)
    for index in np.flatnonzero(active):
        left = cumulative[index, width - lags]
        right = cumulative[index, width] - cumulative[index, lags]
        normalizer = np.sqrt(np.maximum(left * right, 1e-30))
        values = correlation[index, lags] / normalizer
        peaks, _ = find_peaks(values)
        if not len(peaks):
            continue
        best = float(np.max(values[peaks]))
        if best < .6:
            continue
        # Prefer the first strong peak so octave multiples do not win by noise.
        peak = int(next(p for p in peaks if values[p] >= max(.6, .9 * best)))
        lag = float(lags[peak])
        before, center, after = values[peak - 1:peak + 2]
        denominator = before - 2 * center + after
        if abs(denominator) > 1e-12:
            lag += float(np.clip(.5 * (before - after) / denominator, -.5, .5))
        result[index] = sample_rate / lag
    return result


def _mel_bank(frequencies: np.ndarray, count: int = 26) -> np.ndarray:
    to_mel = lambda hz: 2595 * np.log10(1 + hz / 700)
    points = 700 * (10 ** (np.linspace(0, to_mel(frequencies[-1]), count + 2) / 2595) - 1)
    bank = np.zeros((count, len(frequencies)))
    for index in range(count):
        left = (frequencies - points[index]) / max(points[index + 1] - points[index], 1e-12)
        right = (points[index + 2] - frequencies) / max(points[index + 2] - points[index + 1], 1e-12)
        bank[index] = np.maximum(0, np.minimum(left, right))
    return bank


def extract_features(audio: np.ndarray, sample_rate: int) -> dict:
    """Return bounded JSON features on the recording's actual elapsed time axis.

    Analysis uses 40 ms frames / 20 ms hops, downsampled only for display.
    RMS is voiced-median-relative dB (active-median fallback when pitch is absent).
    Unvoiced pitch values are null. Silence has finite diagnostics and no pitch.
    """
    samples = validate_audio(audio, sample_rate)
    peak = float(np.max(np.abs(samples)))
    normalized = samples / peak if peak else samples.copy()
    width = max(8, round(.04 * sample_rate))
    hop = max(1, round(.02 * sample_rate))
    padded = np.pad(normalized, (width // 2, width // 2))
    frames = np.lib.stride_tricks.sliding_window_view(padded, width)[::hop].copy()
    times = np.minimum(np.arange(len(frames)) * hop / sample_rate, len(samples) / sample_rate)
    rms = np.sqrt(np.mean(frames * frames, axis=1))
    active = (rms > np.max(rms) * 10 ** (-50 / 20)) & (rms > 0)
    centered = frames - np.mean(frames, axis=1, keepdims=True)
    pitch = _pitch(centered, sample_rate, active)
    voiced = np.isfinite(pitch)
    baseline_mask = voiced if np.any(voiced) else active
    median_rms = float(np.median(rms[baseline_mask])) if np.any(baseline_mask) else 1.0
    rms_db = 20 * np.log10(np.maximum(rms / median_rms, 1e-6))
    pitch_st = np.full(len(pitch), np.nan)
    if np.any(voiced):
        semitones = 12 * np.log2(pitch[voiced])
        pitch_st[voiced] = semitones - np.median(semitones)
    fft_size = next_fast_len(width)
    spectrum = np.abs(rfft(centered * np.hanning(width), n=fft_size))
    frequencies = rfftfreq(fft_size, 1 / sample_rate)
    mass = np.sum(spectrum, axis=1)
    centroid = np.divide(spectrum @ frequencies, mass, out=np.zeros(len(frames)), where=mass > 1e-20)
    if np.any(active):
        mel_power = (spectrum[active] ** 2) @ _mel_bank(frequencies).T
        mfcc = np.median(dct(np.log(np.maximum(mel_power, 1e-12)), type=2, norm="ortho", axis=1)[:, :13], axis=0)
    else:
        mfcc = np.zeros(13)
    display = np.unique(np.linspace(0, len(frames) - 1, min(1200, len(frames))).astype(int))
    bounds = np.linspace(0, len(samples), min(600, len(samples)) + 1).astype(int)
    waveform = [{"t": round((a + b) / (2 * sample_rate), 5), "min": round(float(np.min(samples[a:b])), 7), "max": round(float(np.max(samples[a:b])), 7)} for a, b in zip(bounds[:-1], bounds[1:])]
    return {
        "times": np.round(times[display], 5).tolist(),
        "rms_db": np.round(rms_db[display], 4).tolist(),
        "pitch_st": [round(float(pitch_st[index]), 4) if voiced[index] else None for index in display],
        "spectral_centroid": np.round(centroid[display], 3).tolist(),
        "mfcc_summary": np.round(mfcc, 5).tolist(),
        "waveform": waveform,
        "voiced_fraction": round(float(np.mean(voiced)), 4),
    }
