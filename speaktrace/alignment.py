"""Local wav2vec2 emissions and constrained CTC word alignment.

The Viterbi path uses audio emissions only. Dataset transformation manifests are
never consumed here. Timing resolution is about 20 ms, not sample accuracy.
"""
from __future__ import annotations

import hashlib
import gc
import json
import os
from pathlib import Path
import re
import threading
import unicodedata

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODEL_DIR = PROJECT_ROOT / ".models" / "wav2vec2-base-960h"
CACHE_DIR = PROJECT_ROOT / ".cache" / "alignments"
MODEL_ID = "facebook/wav2vec2-base-960h"
ALIGNMENT_VERSION = "ctc-viterbi-2-device"
_model = None
_processor = None
_runtime = None
_model_lock = threading.RLock()


def normalize_transcript(text: str) -> list[str]:
    if not isinstance(text, str) or len(text) > 1600:
        raise ValueError("Enter an English transcript of no more than 1600 characters.")
    text = unicodedata.normalize("NFKC", text).replace("’", "'").replace("‘", "'")
    if re.search(r"\d", text):
        raise ValueError("Write numbers as they are spoken, for example 'twenty' instead of '20'.")
    if any(character.isalpha() and not character.isascii() for character in text):
        raise ValueError("This version aligns English speech. Use an English transcript with Latin letters.")
    words = re.findall(r"[A-Za-z]+(?:'[A-Za-z]+)*", text.upper())
    if not 1 <= len(words) <= 150:
        raise ValueError("Enter the exact spoken transcript, between 1 and 150 words.")
    return words


def transcript_similarity(expected: str, recognized: str) -> float:
    a = re.findall(r"[A-Z]+(?:'[A-Z]+)*", expected.upper())
    b = re.findall(r"[A-Z]+(?:'[A-Z]+)*", recognized.upper())
    if not a:
        return 0.0
    row = list(range(len(b) + 1))
    for i, word in enumerate(a, 1):
        next_row = [i]
        for j, other in enumerate(b, 1):
            next_row.append(min(row[j] + 1, next_row[j - 1] + 1, row[j - 1] + (word != other)))
        row = next_row
    return max(0.0, 1.0 - row[-1] / max(len(a), len(b), 1))


def ctc_align(log_probs: np.ndarray, tokens: list[int], blank_id: int = 0) -> list[dict]:
    """Return token frame spans from a standard blank-interleaved CTC Viterbi path."""
    emissions = np.asarray(log_probs, dtype=np.float32)
    if emissions.ndim != 2 or not np.isfinite(emissions).all() or not tokens:
        raise ValueError("Cannot align invalid acoustic emissions or an empty transcript.")
    n_frames, vocabulary_size = emissions.shape
    if any(t < 0 or t >= vocabulary_size or t == blank_id for t in tokens):
        raise ValueError("Cannot align unknown or blank transcript tokens.")
    min_frames = len(tokens) + sum(x == y for x, y in zip(tokens, tokens[1:]))
    if n_frames < min_frames:
        raise ValueError("Cannot align this transcript: the recording is too short for its words.")
    states = np.full(2 * len(tokens) + 1, blank_id, dtype=np.int32)
    states[1::2] = tokens
    count = len(states)
    skip_allowed = np.zeros(count, dtype=bool)
    skip_allowed[2:] = (states[2:] != blank_id) & (states[2:] != states[:-2])
    previous = np.full(count, -np.inf, dtype=np.float32)
    previous[0] = emissions[0, blank_id]
    previous[1] = emissions[0, states[1]]
    back = np.zeros((n_frames, count), dtype=np.uint8)
    for t in range(1, n_frames):
        step = np.full(count, -np.inf, dtype=np.float32)
        skip = np.full(count, -np.inf, dtype=np.float32)
        step[1:] = previous[:-1]
        skip[2:] = previous[:-2]
        skip[~skip_allowed] = -np.inf
        candidates = np.stack((previous, step, skip))
        choices = candidates.argmax(axis=0)
        back[t] = choices
        previous = candidates[choices, np.arange(count)] + emissions[t, states]
    state = count - 1 if previous[-1] > previous[-2] else count - 2
    if not np.isfinite(previous[state]):
        raise ValueError("Cannot align this transcript to the recording.")
    path = np.empty(n_frames, dtype=np.int32)
    for t in range(n_frames - 1, -1, -1):
        path[t] = state
        if t:
            state -= int(back[t, state])
    spans = []
    for i, token in enumerate(tokens):
        frames = np.flatnonzero(path == 2 * i + 1)
        if not len(frames):
            raise ValueError("Cannot align all transcript characters reliably.")
        spans.append({"start": int(frames[0]), "end": int(frames[-1] + 1),
                      "score": float(np.exp(emissions[frames, token]).mean())})
    return spans


def model_ready() -> bool:
    return (MODEL_DIR / "config.json").is_file() and any(
        (MODEL_DIR / name).is_file() for name in ("model.safetensors", "pytorch_model.bin")
    )


def model_revision() -> str:
    meta = MODEL_DIR / "speaktrace-model.json"
    if meta.is_file():
        return str(json.loads(meta.read_text(encoding="utf-8")).get("revision", "local"))
    return "local-unversioned"


def runtime_metadata() -> dict:
    """Return the selected local backend, including persistent CPU fallback.

    This does not load the speech model. Alignment results carry their own copy
    so cached GPU results can never be mislabeled as CPU inference (or vice versa).
    """
    global _runtime
    with _model_lock:
        if _runtime is None:
            import torch
            requested = os.environ.get("SPEAKTRACE_DEVICE", "auto").lower()
            if requested not in ("auto", "cpu", "cuda"):
                raise ValueError("Choose an alignment device: auto, cpu or cuda.")
            available = torch.cuda.is_available() if requested != "cpu" else False
            device = "cuda" if available else "cpu"
            reason = ("CUDA was requested but is unavailable. Using CPU; run setup-gpu.bat to install GPU support."
                      if requested == "cuda" and not available else None)
            _runtime = {"requested_device": requested, "device": device,
                "device_name": torch.cuda.get_device_name(0) if device == "cuda" else "CPU",
                "precision": "float32", "torch_version": str(torch.__version__),
                "cuda_version": torch.version.cuda, "fallback_reason": reason,
                "warnings": [reason] if reason else []}
        return {**_runtime, "warnings": list(_runtime["warnings"])}


def _fallback_to_cpu() -> None:
    """Release GPU storage after the failed call's traceback has been discarded."""
    import torch
    runtime_metadata()
    if _model is not None:
        _model.to("cpu")
    gc.collect()
    torch.cuda.empty_cache()
    reason = "GPU memory was exhausted. This analysis and subsequent alignments use CPU until the server restarts."
    _runtime.update(device="cpu", device_name="CPU", fallback_reason=reason, warnings=[reason])


def _load_model():
    global _model, _processor
    with _model_lock:
        if _model is None:
            if not model_ready():
                raise RuntimeError("The free speech model is not installed yet. Run setup.bat or python scripts/download_model.py, then try again.")
            os.environ.setdefault("HF_HOME", str(PROJECT_ROOT / ".cache" / "huggingface"))
            os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
            import torch
            from transformers import Wav2Vec2ForCTC, Wav2Vec2Processor

            torch.set_num_threads(max(1, min(4, os.cpu_count() or 2)))
            torch.manual_seed(0)
            # Keep CPU/GPU provenance comparable: no half precision or TF32.
            torch.backends.cuda.matmul.allow_tf32 = False
            torch.backends.cudnn.allow_tf32 = False
            _processor = Wav2Vec2Processor.from_pretrained(str(MODEL_DIR), local_files_only=True)
            _model = Wav2Vec2ForCTC.from_pretrained(str(MODEL_DIR), local_files_only=True)
            device = runtime_metadata()["device"]
            out_of_memory = False
            try:
                _model.to(device).eval()
            except torch.cuda.OutOfMemoryError:
                if device != "cuda":
                    raise
                out_of_memory = True
            if out_of_memory:
                _fallback_to_cpu()
                _model.eval()
        return _model, _processor


def _infer_once(model, processor, audio, sample_rate, device):
    import torch
    inputs = processor(np.asarray(audio, dtype=np.float32), sampling_rate=sample_rate, return_tensors="pt")
    values = inputs.input_values.to(device=device, dtype=torch.float32)
    logits = model(values).logits[0]
    log_probs = torch.log_softmax(logits, dim=-1).cpu().numpy()
    recognized = processor.decode(logits.argmax(dim=-1).cpu())
    return log_probs, recognized


def _emissions(audio: np.ndarray, sample_rate: int):
    if sample_rate != 16000:
        raise ValueError("Alignment expects audio resampled to 16 kHz.")
    import torch

    with _model_lock, torch.inference_mode():
        model, processor = _load_model()
        device = runtime_metadata()["device"]
        out_of_memory = False
        try:
            log_probs, recognized = _infer_once(model, processor, audio, sample_rate, device)
        except torch.cuda.OutOfMemoryError:
            if device != "cuda":
                raise
            out_of_memory = True
        # Retry outside the except block: traceback tensor references must be gone.
        if out_of_memory:
            _fallback_to_cpu()
            log_probs, recognized = _infer_once(model, processor, audio, sample_rate, "cpu")
        return log_probs, recognized, processor, runtime_metadata()


def transcribe_audio(audio: np.ndarray, sample_rate: int = 16000) -> str:
    """Development helper for locating archive excerpts; no synthetic timings."""
    _, recognized, _, _ = _emissions(audio, sample_rate)
    return recognized


def align_audio(audio: np.ndarray, sample_rate: int, transcript: str, *, use_cache: bool = True) -> dict:
    from .audio import validate_waveform

    validate_waveform(audio, sample_rate)
    words = normalize_transcript(transcript)
    text = "|".join(words)
    def cache_file(compute):
        key = hashlib.sha256(np.asarray(audio, dtype="<f4").tobytes())
        key.update(f"{sample_rate}|{text}|{model_revision()}|{ALIGNMENT_VERSION}".encode())
        key.update(json.dumps({k: compute[k] for k in ("device", "device_name", "precision", "torch_version", "cuda_version")}, sort_keys=True).encode())
        return CACHE_DIR / f"{key.hexdigest()}.json"

    cache_path = cache_file(runtime_metadata())
    if use_cache and cache_path.is_file():
        cached = json.loads(cache_path.read_text(encoding="utf-8"))
        cached["cached"] = True
        return cached
    emissions, recognized, processor, compute = _emissions(audio, sample_rate)
    vocabulary = processor.tokenizer.get_vocab()
    if any(character not in vocabulary for character in text):
        raise ValueError("Transcript contains characters the English aligner cannot read.")
    spans = ctc_align(emissions, [vocabulary[c] for c in text], processor.tokenizer.pad_token_id)
    seconds_per_frame = (len(audio) / sample_rate) / len(emissions)
    aligned_words = []
    position = 0
    for word in words:
        character_spans = spans[position:position + len(word)]
        aligned_words.append({
            "word": word.lower(),
            "start": round(character_spans[0]["start"] * seconds_per_frame, 4),
            "end": round(character_spans[-1]["end"] * seconds_per_frame, 4),
            "score": round(float(np.mean([span["score"] for span in character_spans])), 4),
        })
        position += len(word) + 1
    result = {
        "words": aligned_words,
        "confidence": round(float(np.mean([w["score"] for w in aligned_words])), 4),
        "coverage": round(float(np.mean([w["score"] >= 0.35 for w in aligned_words])), 4),
        "recognized_text": recognized,
        "transcript_agreement": round(transcript_similarity(" ".join(words), recognized), 4),
        "model": MODEL_ID, "revision": model_revision(), "alignment_version": ALIGNMENT_VERSION,
        "cached": False, "compute": compute,
    }
    if use_cache:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_file(compute).write_text(json.dumps(result, indent=2, allow_nan=False), encoding="utf-8")
    return result
