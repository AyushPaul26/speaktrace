from speaktrace.pipeline import apply_alignment_policy
from speaktrace.reports import html_report


def comparison():
    return {"summary": {"score": 88, "status": "complete", "flag_count": 1, "caption": "Measured", "dimensions": [{"score": 88}]}, "findings": [{"id": "one"}], "warnings": []}


def test_wrong_transcript_withholds_scores_and_findings():
    result = comparison()
    apply_alignment_policy(result, {"transcript_agreement": 0.9}, {"transcript_agreement": 0.2})
    assert result["summary"]["score"] is None
    assert result["summary"]["status"] == "unreliable"
    assert result["findings"] == []
    assert result["summary"]["dimensions"][0]["score"] is None


def test_partial_agreement_warns_without_inventing_new_findings():
    result = comparison()
    apply_alignment_policy(result, {"transcript_agreement": 0.9}, {"transcript_agreement": 0.65})
    assert result["summary"]["score"] == 88
    assert len(result["findings"]) == 1
    assert result["warnings"]


def test_pipeline_keeps_both_alignment_devices_and_oom_warning(monkeypatch, tmp_path):
    import numpy as np
    from speaktrace.pipeline import run_analysis
    gpu = {"device": "cuda", "device_name": "Test GPU", "precision": "float32", "warnings": []}
    cpu = {"device": "cpu", "device_name": "CPU", "precision": "float32", "warnings": ["GPU memory exhausted; using CPU."]}
    metadata = iter([gpu, cpu])
    analyzed = []
    def align(*args, **kwargs):
        analyzed.append(args[0].copy())
        return {"words": [{"word": "hello", "start": 0.1, "end": 1.0, "score": 0.99}],
            "confidence": 0.99, "coverage": 1.0, "transcript_agreement": 1.0,
            "recognized_text": "HELLO", "cached": False, "compute": next(metadata)}
    monkeypatch.setattr("speaktrace.pipeline.align_audio", align)
    monkeypatch.setattr("speaktrace.pipeline.runtime_metadata", lambda: cpu)
    monkeypatch.setattr("speaktrace.core.features.extract_features", lambda *args: {})
    monkeypatch.setattr("speaktrace.core.comparison.compare_recordings", lambda *args: comparison())
    audio = (2 * np.sin(np.arange(32000) * 0.1)).astype(np.float32)
    result = run_analysis("example", tmp_path, lambda *args: None, reference_audio=audio,
        participant_audio=audio, transcript="hello", reference_name="Reference", participant_name="Participant")
    assert result["compute"]["device"] == "cuda+cpu"
    assert result["reference"]["alignment"]["compute"]["device"] == "cuda"
    assert result["participant"]["alignment"]["compute"]["device"] == "cpu"
    assert "GPU memory exhausted; using CPU." in result["warnings"]
    import soundfile as sf
    for index, role in enumerate(("reference", "participant")):
        playback, _ = sf.read(tmp_path / f"{role}.wav", dtype="float32")
        np.testing.assert_array_equal(analyzed[index], playback)
    assert result["audio_processing"]["reference_gain"] < 1
