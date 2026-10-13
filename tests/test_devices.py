"""Backend selection and fallback must preserve real execution provenance."""
from types import SimpleNamespace

import numpy as np
import pytest
import torch

from speaktrace import alignment


@pytest.fixture(autouse=True)
def isolated_runtime(monkeypatch):
    monkeypatch.setattr(alignment, "_model", None)
    monkeypatch.setattr(alignment, "_processor", None)
    monkeypatch.setattr(alignment, "_runtime", None, raising=False)
    monkeypatch.setenv("SPEAKTRACE_DEVICE", "auto")
    monkeypatch.setattr(torch.cuda, "get_device_name", lambda _: "Test GPU")


@pytest.mark.parametrize("requested,available,device", [
    ("auto", True, "cuda"), ("auto", False, "cpu"),
    ("cpu", True, "cpu"), ("cuda", False, "cpu"),
])
def test_device_selection_reports_actual_backend(monkeypatch, requested, available, device):
    monkeypatch.setenv("SPEAKTRACE_DEVICE", requested)
    monkeypatch.setattr(torch.cuda, "is_available", lambda: available)
    info = alignment.runtime_metadata()
    assert info["device"] == device
    assert info["requested_device"] == requested
    assert info["precision"] == "float32"
    assert bool(info["warnings"]) == (requested == "cuda" and not available)


def test_invalid_device_is_rejected(monkeypatch):
    monkeypatch.setenv("SPEAKTRACE_DEVICE", "typo")
    with pytest.raises(ValueError, match="auto.*cpu.*cuda"):
        alignment.runtime_metadata()


def test_cuda_oom_retries_on_cpu_and_records_fallback(monkeypatch):
    monkeypatch.setattr(torch.cuda, "is_available", lambda: True)
    monkeypatch.setattr(torch.cuda, "empty_cache", lambda: None)
    model = SimpleNamespace(to=lambda device: model)
    processor = object()
    monkeypatch.setattr(alignment, "_model", model)
    monkeypatch.setattr(alignment, "_load_model", lambda: (model, processor))

    def infer(model, processor, audio, sample_rate, device):
        assert torch.is_inference_mode_enabled()
        if device == "cuda":
            raise torch.cuda.OutOfMemoryError("simulated allocator exhaustion")
        return np.array([[-1.0, -2.0]], dtype=np.float32), "HELLO"

    monkeypatch.setattr(alignment, "_infer_once", infer, raising=False)
    emissions, recognized, _, compute = alignment._emissions(np.ones(32000), 16000)
    assert emissions.tolist() == [[-1.0, -2.0]]
    assert recognized == "HELLO"
    assert compute["device"] == "cpu"
    assert "memory" in compute["fallback_reason"].lower()
    assert alignment.runtime_metadata()["device"] == "cpu"
    assert alignment._emissions(np.ones(32000), 16000)[3]["device"] == "cpu"


def test_non_oom_model_failure_is_not_disguised_as_cpu_fallback(monkeypatch):
    monkeypatch.setattr(torch.cuda, "is_available", lambda: True)
    monkeypatch.setattr(alignment, "_load_model", lambda: (object(), object()))

    def fail(*args):
        raise RuntimeError("invalid tensor shape")

    monkeypatch.setattr(alignment, "_infer_once", fail, raising=False)
    with pytest.raises(RuntimeError, match="invalid tensor shape"):
        alignment._emissions(np.ones(32000), 16000)
    assert alignment.runtime_metadata()["device"] == "cuda"


def test_cache_separates_backend_and_returns_original_provenance(monkeypatch, tmp_path):
    monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
    monkeypatch.setattr(alignment, "CACHE_DIR", tmp_path)
    processor = SimpleNamespace(tokenizer=SimpleNamespace(get_vocab=lambda: {"A": 1}, pad_token_id=0))

    def infer(*args):
        return np.array([[-0.01, -8], [-8, -0.01], [-0.01, -8]], dtype=np.float32), "A", processor, alignment.runtime_metadata()

    monkeypatch.setattr(alignment, "_emissions", infer)
    audio = np.sin(np.arange(32000) * 0.1).astype(np.float32)
    first = alignment.align_audio(audio, 16000, "A")
    cached = alignment.align_audio(audio, 16000, "A")
    assert not first["cached"] and cached["cached"]
    assert cached["compute"]["device"] == "cpu"
    monkeypatch.setattr(alignment, "_runtime", None)
    monkeypatch.setattr(torch.cuda, "is_available", lambda: True)
    gpu = alignment.align_audio(audio, 16000, "A")
    assert not gpu["cached"]
    assert gpu["compute"]["device"] == "cuda"
    assert len(list(tmp_path.glob("*.json"))) == 2


def test_fallback_alignment_is_cached_under_its_cpu_backend(monkeypatch, tmp_path):
    monkeypatch.setattr(torch.cuda, "is_available", lambda: True)
    monkeypatch.setattr(alignment, "CACHE_DIR", tmp_path)
    processor = SimpleNamespace(tokenizer=SimpleNamespace(get_vocab=lambda: {"A": 1}, pad_token_id=0))

    def infer(*args):
        alignment._runtime.update(device="cpu", device_name="CPU", fallback_reason="GPU memory exhausted.",
                                  warnings=["GPU memory exhausted."])
        return np.array([[-0.01, -8], [-8, -0.01], [-0.01, -8]], dtype=np.float32), "A", processor, alignment.runtime_metadata()

    monkeypatch.setattr(alignment, "_emissions", infer)
    audio = np.sin(np.arange(32000) * 0.1).astype(np.float32)
    first = alignment.align_audio(audio, 16000, "A")
    assert first["compute"]["device"] == "cpu"
    second = alignment.align_audio(audio, 16000, "A")
    assert second["cached"]
    assert second["compute"]["device"] == "cpu"
    assert second["compute"]["fallback_reason"] == "GPU memory exhausted."
