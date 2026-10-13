"""Compose measured alignment and acoustic comparison into an auditable result."""
from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
import time

import numpy as np

from .alignment import align_audio, MODEL_ID, model_revision, runtime_metadata
from .audio import write_wav, canonical_pcm


def apply_alignment_policy(comparison: dict, reference_alignment: dict, participant_alignment: dict) -> dict:
    """Share the application's independent transcript gate with evaluation."""
    agreement = min(reference_alignment["transcript_agreement"], participant_alignment["transcript_agreement"])
    if agreement < 0.45:
        comparison["summary"].update(score=None, status="unreliable", flag_count=0,
            caption="Scoring withheld: the supplied transcript does not match enough of the recognized speech.")
        for dimension in comparison["summary"]["dimensions"]:
            dimension["score"] = None
        comparison["findings"] = []
        comparison["warnings"].append("Transcript agreement is below 45%. Check that both recordings contain the exact same supplied words, without introductions or missing phrases.")
    elif agreement < 0.75:
        comparison["warnings"].append("Some spoken words differ from the transcript or were unclear. Review the highlighted words before interpreting the scores.")
    return comparison


def run_analysis(identifier: str, directory: Path, progress, *, reference_audio: np.ndarray,
                 participant_audio: np.ndarray, transcript: str, reference_name: str,
                 participant_name: str, weights: dict | None = None, title: str = "Your comparison",
                 mode: str = "upload", provenance: dict | None = None) -> dict:
    from .core.features import extract_features
    from .core.comparison import compare_recordings

    start = time.perf_counter()
    sample_rate = 16000
    reference_audio, reference_gain = canonical_pcm(reference_audio, sample_rate)
    participant_audio, participant_gain = canonical_pcm(participant_audio, sample_rate)
    write_wav(directory / "reference.wav", reference_audio)
    write_wav(directory / "participant.wav", participant_audio)
    def device_label():
        return "GPU" if runtime_metadata()["device"] == "cuda" else "CPU"
    progress(f"Aligning reference words on {device_label()}", 15)
    ref_alignment = align_audio(reference_audio, sample_rate, transcript, use_cache=mode == "demo")
    progress(f"Aligning participant words on {device_label()}", 42)
    participant_alignment = align_audio(participant_audio, sample_rate, transcript, use_cache=mode == "demo")
    progress("Measuring pacing, pauses and energy", 70)
    comparison = compare_recordings(reference_audio, participant_audio, sample_rate,
        ref_alignment["words"], participant_alignment["words"], transcript, weights)
    # Constrained CTC can force incorrect text onto sound. A separate greedy decode
    # agreement gate avoids treating a mathematically possible path as good evidence.
    apply_alignment_policy(comparison, ref_alignment, participant_alignment)
    progress("Preparing evidence and report", 88)
    recordings = []
    for name, role, audio, aligned in ((reference_name, "reference", reference_audio, ref_alignment),
                                     (participant_name, "participant", participant_audio, participant_alignment)):
        recordings.append({"name": name, "url": f"/media/jobs/{identifier}/{role}.wav",
            "duration": round(len(audio) / sample_rate, 4), "words": aligned["words"],
            "features": extract_features(audio, sample_rate),
            "alignment": {k: aligned[k] for k in ("confidence", "coverage", "transcript_agreement", "recognized_text", "cached", "compute")}})
    runtime = runtime_metadata()
    alignment_runs = {"reference": {**ref_alignment["compute"], "cached": ref_alignment["cached"]},
                      "participant": {**participant_alignment["compute"], "cached": participant_alignment["cached"]}}
    devices = {run["device"] for run in alignment_runs.values()}
    device = next(iter(devices)) if len(devices) == 1 else "cuda+cpu"
    for role, info in [(None, runtime), *alignment_runs.items()]:
        for warning in info.get("warnings", []):
            if warning not in comparison["warnings"]:
                comparison["warnings"].append(
                    f"Cached {role} alignment: {warning}" if info.get("cached") else warning)
    result = {"id": identifier, "title": title, "created_at": datetime.now(timezone.utc).isoformat(),
        "transcript": transcript, "mode": mode,
        "audio_processing": {"sample_rate": sample_rate, "encoding": "PCM_16",
            "reference_gain": reference_gain, "participant_gain": participant_gain,
            "note": "Measurements use the exact stored playback samples. Uniform gain prevents clipping or excessive quantization loss."},
        "compute": {**runtime, "device": device, "runtime_device": runtime["device"],
            "device_name": " / ".join(dict.fromkeys(run["device_name"] for run in alignment_runs.values())),
            "alignment_runs": alignment_runs, "feature_device": "cpu",
            "alignment": "wav2vec2-ctc", "seconds": round(time.perf_counter() - start, 2),
            "model": MODEL_ID, "revision": model_revision(),
            "cached_alignment": ref_alignment["cached"] or participant_alignment["cached"]},
        "reference": recordings[0], "participant": recordings[1], **comparison}
    if provenance:
        result["provenance"] = provenance
    return result
