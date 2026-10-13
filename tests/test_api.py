"""Exercise actual local HTTP validation and job boundaries without downloading models."""
import io
import wave
import numpy as np
import pytest
from fastapi.testclient import TestClient

from speaktrace.api import create_app


@pytest.fixture
def client(tmp_path):
    (tmp_path / "web").mkdir()
    (tmp_path / "web" / "index.html").write_text("<title>SpeakTrace</title>", encoding="utf-8")
    with TestClient(create_app(tmp_path)) as test_client:
        yield test_client


def test_health_is_available_without_model_download(client, monkeypatch):
    monkeypatch.setattr("speaktrace.api.runtime_metadata", lambda: {"device": "cuda", "device_name": "Test GPU", "precision": "float32", "warnings": []})
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["device"] == "cuda"
    assert response.json()["device_name"] == "Test GPU"
    assert client.get("/api/demos").json() == {"demos": []}


def test_unknown_demo_and_job_return_useful_not_found(client):
    assert client.get("/api/jobs/not-a-job").status_code == 404
    assert client.post("/api/demos/not-a-demo/analyze", json={"variant_id": "clean"}).status_code == 404


def test_cross_origin_write_is_rejected(client):
    response = client.post("/api/demos/demo/analyze", headers={"Origin": "https://untrusted.example"}, json={"variant_id": "clean"})
    assert response.status_code == 403


def test_invalid_audio_and_transcript_create_no_job(client):
    response = client.post("/api/analyze", data={"transcript": "hello there"}, files={
        "reference": ("a.wav", b"bad", "audio/wav"),
        "participant": ("b.wav", b"bad", "audio/wav")})
    assert response.status_code == 422
    assert "decode" in response.json()["detail"].lower()


def test_path_traversal_never_exposes_project_files(client):
    assert client.get("/media/%2e%2e/docs/API.md").status_code == 404
    assert client.get("/api/results/unknown/report").status_code == 404


def test_nonfinite_or_negative_weights_rejected(client):
    response = client.post("/api/demos/missing/analyze", json={"variant_id": "clean", "weights": {"pacing": -1, "pauses": 1, "energy": 1}})
    assert response.status_code == 422


def test_oversized_body_rejected_before_multipart_decode(client):
    response = client.post("/api/analyze", content=b"x", headers={"Content-Length": "50000000"})
    assert response.status_code == 413


def test_chunked_request_cannot_bypass_body_limit(client, monkeypatch):
    monkeypatch.setattr("speaktrace.api.MAX_REQUEST_BYTES", 200)
    def chunks():
        yield b"a" * 150
        yield b"b" * 150
    response = client.post("/api/analyze", content=chunks(), headers={"content-type": "application/x-www-form-urlencoded"})
    assert response.status_code == 413
