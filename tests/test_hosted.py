"""Hosted transport boundaries, real rubric reuse, and request-file cleanup."""
import io
import json
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from api.hosted import create_app


ORIGIN = {"Origin": "http://testserver"}
TRANSCRIPT = "one two three four five six"


def wav_bytes(*, seconds=3, rate=16000, channels=1, subtype="PCM_16", peak=.2):
    audio = peak * np.sin(np.arange(round(seconds * rate)) * .1)
    if channels == 2:
        audio = np.stack([audio, audio], axis=1)
    buffer = io.BytesIO()
    sf.write(buffer, audio, rate, format="WAV", subtype=subtype)
    return buffer.getvalue()


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path)) as value:
        yield value


def upload(client, content=None, **kwargs):
    content = wav_bytes() if content is None else content
    return client.post("/api/hosted/analyze", headers=ORIGIN,
        files={"reference": ("reference.wav", content, "audio/wav"),
               "participant": ("practice.wav", content, "audio/wav")},
        data={"transcript": TRANSCRIPT, **kwargs})


def test_hosted_rejects_cross_origin_and_missing_origin(client):
    for headers in ({"Origin": "https://elsewhere.example"}, {}):
        response = client.post("/api/hosted/analyze", headers=headers)
        assert response.status_code == 403


def test_hosted_bounds_body_before_multipart_parsing(client):
    response = client.post("/api/hosted/analyze", headers={**ORIGIN, "Content-Length": "4200001"}, content=b"x")
    assert response.status_code == 413


def test_chunked_body_cannot_bypass_hosted_limit(client):
    def chunks():
        yield b"x" * 2_100_001
        yield b"y" * 2_100_001
    response = client.post("/api/hosted/analyze", headers={**ORIGIN, "Content-Type": "application/octet-stream"}, content=chunks())
    assert response.status_code == 413


@pytest.mark.parametrize("options", [{"rate": 48000}, {"channels": 2}, {"subtype": "FLOAT"}, {"peak": .001}, {"seconds": 61}])
def test_hosted_requires_bounded_canonical_audio(client, options):
    response = upload(client, wav_bytes(**options))
    assert response.status_code == 422


@pytest.mark.parametrize("seconds", [30 + 1 / 16000, 31])
def test_hosted_rejects_audio_over_thirty_seconds_before_inference(client, seconds, monkeypatch):
    monkeypatch.setattr("api.hosted.model_ready", lambda: False)
    response = upload(client, wav_bytes(seconds=seconds))
    assert response.status_code == 422
    assert "30 seconds" in response.json()["detail"]


def test_hosted_rejects_invalid_transcript_and_weights(client):
    assert upload(client, transcript="123").status_code == 422
    assert upload(client, weights='{"pacing":0,"pauses":0,"energy":0}').status_code == 422
    assert upload(client, weights='{"pacing":false,"pauses":1,"energy":1}').status_code == 422


def test_hosted_health_and_method_explain_remote_processing(client):
    data = client.get("/api/health").json()
    assert data["deployment"] == "vercel"
    assert data["synchronous"] is True
    assert data["max_seconds"] == 30
    method = client.get("/api/methodology").json()
    assert "server" in method["retention"].lower()
    assert method["rubric"]["version"] == "reference-relative-1.1.0"


def test_hosted_serves_studio_when_static_cdn_does_not_handle_root(tmp_path):
    (tmp_path / "web").mkdir()
    (tmp_path / "web/index.html").write_text("<title>SpeakTrace studio</title>", encoding="utf-8")
    with TestClient(create_app(tmp_path)) as client:
        response = client.get("/")
        assert response.status_code == 200
        assert "SpeakTrace studio" in response.text
        assert response.headers["content-type"].startswith("text/html")


def test_hosted_preparation_lowers_threads_after_model_loader(monkeypatch):
    import torch
    import api.hosted as hosted
    before = torch.get_num_threads()
    monkeypatch.setattr("speaktrace.alignment._load_model", lambda: torch.set_num_threads(4))
    try:
        assert hasattr(hosted, "_prepare_runtime")
        hosted._prepare_runtime()
        assert torch.get_num_threads() == 1
    finally:
        torch.set_num_threads(before)


@pytest.fixture
def aligned_pipeline(monkeypatch):
    """Only replace expensive pretrained inference, keeping the pipeline and DSP real."""
    compute = {"device": "cpu", "device_name": "CPU", "precision": "float32", "warnings": []}
    def align(audio, sample_rate, transcript, *, use_cache):
        assert not use_cache
        return {"words": [{"word": word, "start": .05 + i * .5, "end": .4 + i * .5, "score": .99}
                          for i, word in enumerate(TRANSCRIPT.split())],
                "confidence": .99, "coverage": 1., "transcript_agreement": 1.,
                "recognized_text": TRANSCRIPT.upper(), "cached": False, "compute": compute}
    monkeypatch.setattr("api.hosted.model_ready", lambda: True)
    monkeypatch.setattr("api.hosted._prepare_runtime", lambda: None, raising=False)
    monkeypatch.setattr("speaktrace.pipeline.align_audio", align)
    monkeypatch.setattr("speaktrace.pipeline.runtime_metadata", lambda: compute)
    directories = []
    from speaktrace.audio import write_wav
    def track_write(path, *args):
        directories.append(path.parent)
        write_wav(path, *args)
    monkeypatch.setattr("speaktrace.pipeline.write_wav", track_write)
    return directories


def test_hosted_uses_real_rubric_and_removes_request_audio(client, aligned_pipeline):
    response = upload(client, weights='{"pacing":0,"pauses":100,"energy":0}')
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["summary"]["score"] == 100
    assert result["rubric"]["weights"] == {"pacing": 0, "pauses": 1, "energy": 0}
    assert result["reference"]["url"] is None
    assert result["participant"]["url"] is None
    assert result["reference"]["name"] == "reference.wav"
    assert result["compute"]["cached_alignment"] is False
    assert result["deployment"] == "vercel"
    assert len(aligned_pipeline) == 2
    assert not any(directory.exists() for directory in aligned_pipeline)
    assert client.get("/api/jobs/" + result["id"]).status_code == 404


def test_hosted_accepts_exactly_thirty_seconds(client, aligned_pipeline):
    response = upload(client, wav_bytes(seconds=30))
    assert response.status_code == 200, response.text
    assert response.json()["reference"]["duration"] == 30
    assert not any(directory.exists() for directory in aligned_pipeline)


def test_hosted_cleans_up_after_alignment_error(client, aligned_pipeline, monkeypatch):
    def fail(*args, **kwargs):
        raise ValueError("Unable to align this speech.")
    monkeypatch.setattr("speaktrace.pipeline.align_audio", fail)
    response = upload(client)
    assert response.status_code == 422
    assert len(aligned_pipeline) == 2
    assert not any(directory.exists() for directory in aligned_pipeline)


def test_hosted_prepares_inside_slot_and_releases_it_after_setup_failure(client, aligned_pipeline, monkeypatch):
    from api.hosted import _analysis_slot
    def fail_preparation():
        assert not _analysis_slot.acquire(blocking=False)
        raise RuntimeError("Model preparation failed")
    monkeypatch.setattr("api.hosted._prepare_runtime", fail_preparation)
    response = upload(client)
    assert response.status_code == 503
    assert aligned_pipeline == []
    monkeypatch.setattr("api.hosted._prepare_runtime", lambda: None)
    assert upload(client).status_code == 200


def test_hosted_demo_uses_public_audio_and_fresh_pipeline(tmp_path, aligned_pipeline):
    for relative in ("data/references/example.wav", "data/variants/example/clean.wav"):
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(wav_bytes())
    (tmp_path / "data/manifest.json").write_text(json.dumps({"references": [{
        "id": "example", "title": "An example", "speaker": "Test", "transcript": TRANSCRIPT,
        "audio": "data/references/example.wav", "license": "Public domain", "source_url": "https://example.org",
        "variants": [{"id": "clean", "label": "Unchanged", "flaw": "clean", "severity": "control",
                      "audio": "data/variants/example/clean.wav"}]}]}), encoding="utf-8")
    with TestClient(create_app(tmp_path)) as client:
        response = client.post("/api/hosted/demos/example/analyze", headers=ORIGIN, json={"variant_id": "clean"})
        assert response.status_code == 200, response.text
        result = response.json()
        assert result["mode"] == "demo"
        assert result["reference"]["url"] == "/data/references/example.wav"
        assert result["participant"]["url"] == "/data/variants/example/clean.wav"
        assert result["compute"]["cached_alignment"] is False
        assert result["provenance"]["synthetic"] is False
    assert not any(directory.exists() for directory in aligned_pipeline)
