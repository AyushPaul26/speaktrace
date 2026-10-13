import io
import wave
import numpy as np
import pytest

from speaktrace.audio import decode_audio, validate_waveform


def pcm_wave(audio, rate=16000):
    stream = io.BytesIO()
    with wave.open(stream, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(rate)
        out.writeframes((audio * 30000).astype("<i2").tobytes())
    return stream.getvalue()


def test_decode_resamples_to_mono_sixteen_kilohertz():
    t = np.arange(48000 * 3) / 48000
    y, rate = decode_audio(pcm_wave(0.2 * np.sin(2 * np.pi * 180 * t), 48000))
    assert rate == 16000
    assert y.ndim == 1
    assert len(y) == 48000
    assert np.isfinite(y).all()


def test_silent_audio_is_rejected():
    with pytest.raises(ValueError, match="silent"):
        validate_waveform(np.zeros(48000), 16000)


def test_corrupt_audio_has_actionable_error():
    with pytest.raises(ValueError, match="decode"):
        decode_audio(b"this is not an audio file")


def test_extreme_duration_rejected_before_processing():
    with pytest.raises(ValueError, match="60"):
        validate_waveform(np.ones(16000 * 61, dtype=np.float32) * 0.1, 16000)


def test_nonfinite_audio_is_rejected():
    y = np.ones(32000, dtype=np.float32) * 0.1
    y[7] = np.nan
    with pytest.raises(ValueError, match="finite"):
        validate_waveform(y, 16000)


@pytest.mark.parametrize('amplitude', [2.0, 0.00003, 0.2])
def test_canonical_pcm_preserves_shape_and_matches_playback(tmp_path, amplitude):
    import soundfile as sf
    from speaktrace.audio import canonical_pcm, write_wav
    original = (amplitude * np.sin(np.arange(48000) * .1)).astype(np.float32)
    canonical, gain = canonical_pcm(original)
    validate_waveform(canonical, 16000)
    assert np.max(abs(canonical)) <= 1
    assert np.max(abs(canonical - original * gain)) <= 1 / 32768 + 1e-7
    path = tmp_path / 'playback.wav'
    write_wav(path, canonical)
    playback, sr = sf.read(path, dtype='float32')
    assert sr == 16000
    np.testing.assert_array_equal(canonical, playback)
