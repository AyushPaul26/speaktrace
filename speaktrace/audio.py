"""Bounded audio decoding. No shell codecs, cloud uploads, or guessed timings."""
from __future__ import annotations

import io
from math import gcd
from pathlib import Path

import numpy as np
from scipy.signal import resample_poly

SAMPLE_RATE = 16000
MAX_BYTES = 20 * 1024 * 1024
MIN_SECONDS = 2.0
MAX_SECONDS = 60.0


def validate_waveform(audio: np.ndarray, sample_rate: int) -> None:
    y = np.asarray(audio)
    if y.ndim != 1 or sample_rate <= 0 or not np.isfinite(y).all():
        raise ValueError("Audio must contain finite mono samples at a valid sample rate.")
    duration = len(y) / sample_rate
    if duration < MIN_SECONDS or duration > MAX_SECONDS:
        raise ValueError("Choose a recording between 2 and 60 seconds long.")
    centered = y.astype(np.float64) - float(np.mean(y))
    if np.sqrt(np.mean(centered * centered)) < 1e-5:
        raise ValueError("This recording is silent or too quiet. Record audible speech and try again.")
    if np.max(np.abs(y)) > 4:
        raise ValueError("Audio sample levels are invalid. Export a standard PCM WAV file.")


def decode_audio(source: bytes | Path | str) -> tuple[np.ndarray, int]:
    import soundfile as sf

    if isinstance(source, bytes):
        if len(source) > MAX_BYTES:
            raise ValueError("Each audio file must be no larger than 20 MB.")
        stream = io.BytesIO(source)
    else:
        path = Path(source)
        if path.stat().st_size > MAX_BYTES:
            raise ValueError("Each audio file must be no larger than 20 MB.")
        stream = path
    try:
        with sf.SoundFile(stream) as sound:
            if sound.channels not in (1, 2):
                raise ValueError("Choose a mono or stereo audio recording.")
            if not 8000 <= sound.samplerate <= 192000:
                raise ValueError("Audio sample rate must be between 8 kHz and 192 kHz.")
            if not MIN_SECONDS <= len(sound) / sound.samplerate <= MAX_SECONDS:
                raise ValueError("Choose a recording between 2 and 60 seconds long.")
            rate = sound.samplerate
            y = sound.read(dtype="float32", always_2d=True).mean(axis=1)
    except (RuntimeError, sf.LibsndfileError) as error:
        raise ValueError("Could not decode this audio. Export it as WAV, FLAC, OGG or MP3 and try again.") from error
    if rate != SAMPLE_RATE:
        divisor = gcd(rate, SAMPLE_RATE)
        y = resample_poly(y, SAMPLE_RATE // divisor, rate // divisor).astype(np.float32)
    validate_waveform(y, SAMPLE_RATE)
    return np.asarray(y, dtype=np.float32), SAMPLE_RATE


def canonical_pcm(audio: np.ndarray, sample_rate: int = SAMPLE_RATE) -> tuple[np.ndarray, float]:
    """Return the exact PCM16 samples used for both playback and measurement.

    A uniform gain protects valid float WAVs from clipping and very quiet files
    from quantization loss. Ordinary in-range audio keeps its original gain.
    """
    import soundfile as sf

    validate_waveform(audio, sample_rate)
    peak = float(np.max(np.abs(audio)))
    gain = 0.95 / peak if peak > 1 or peak < 0.01 else 1.0
    buffer = io.BytesIO()
    sf.write(buffer, np.asarray(audio, dtype=np.float32) * gain, sample_rate, format="WAV", subtype="PCM_16")
    buffer.seek(0)
    canonical, _ = sf.read(buffer, dtype="float32")
    validate_waveform(canonical, sample_rate)
    return canonical, gain


def write_wav(path: Path, audio: np.ndarray, sample_rate: int = SAMPLE_RATE) -> None:
    import soundfile as sf

    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(path, audio, sample_rate, subtype="PCM_16")
