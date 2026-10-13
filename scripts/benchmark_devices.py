"""Measure real, uncached CPU/CUDA alignment and 60-second GPU memory use.

Run after GPU setup, with the studio stopped, to avoid competing GPU allocations.
Every backend uses an isolated process; no training or network calls are made.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def measure(device: str, repetitions: int) -> dict:
    os.environ["SPEAKTRACE_DEVICE"] = device
    import numpy as np
    import torch
    from speaktrace.alignment import align_audio, _emissions, runtime_metadata
    from speaktrace.audio import decode_audio

    runtime = runtime_metadata()
    if runtime["device"] != device:
        raise RuntimeError(f"Requested {device} is unavailable: {runtime['fallback_reason']}")
    manifest = json.loads((ROOT / "data" / "manifest.json").read_text(encoding="utf-8"))
    reference = min(manifest["references"], key=lambda row: row["duration"])
    audio, rate = decode_audio(ROOT / reference["audio"])
    if device == "cuda":
        free, total = torch.cuda.mem_get_info()
        torch.cuda.reset_peak_memory_stats()
        memory_before = {"free_mib": round(free / 2**20, 1), "total_mib": round(total / 2**20, 1)}
    else:
        memory_before = None

    started = time.perf_counter()
    result = align_audio(audio, rate, reference["transcript"], use_cache=False)
    cold_seconds = time.perf_counter() - started
    timings = []
    for _ in range(repetitions):
        started = time.perf_counter()
        result = align_audio(audio, rate, reference["transcript"], use_cache=False)
        timings.append(time.perf_counter() - started)

    output = {"requested_device": device, "compute": result["compute"],
        "source": reference["id"], "source_audio": reference["audio"],
        "source_duration_seconds": len(audio) / rate, "cache_enabled": False,
        "cold_alignment_seconds": round(cold_seconds, 4),
        "warm_alignment_seconds": [round(value, 4) for value in timings],
        "warm_median_seconds": round(statistics.median(timings), 4),
        "alignment": {key: result[key] for key in ("words", "confidence", "coverage", "recognized_text", "transcript_agreement")},
        "memory_before": memory_before}
    if device == "cuda":
        output["clip_peak_allocated_mib"] = round(torch.cuda.max_memory_allocated() / 2**20, 1)
        output["clip_peak_reserved_mib"] = round(torch.cuda.max_memory_reserved() / 2**20, 1)
        torch.cuda.reset_peak_memory_stats()
        long_audio = np.tile(audio, int(np.ceil(60 * rate / len(audio))))[:60 * rate]
        started = time.perf_counter()
        emissions, _, _, stress_compute = _emissions(long_audio, rate)
        output["maximum_length_memory_check"] = {
            "description": "60-second tiled excerpt; inference memory stress only, not speech-quality validation.",
            "audio_seconds": len(long_audio) / rate, "seconds": round(time.perf_counter() - started, 4),
            "emission_frames": len(emissions), "compute": stress_compute,
            "peak_allocated_mib": round(torch.cuda.max_memory_allocated() / 2**20, 1),
            "peak_reserved_mib": round(torch.cuda.max_memory_reserved() / 2**20, 1),
            "completed_on_gpu": stress_compute["device"] == "cuda"}
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device", choices=("both", "cpu", "cuda"), default="both")
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--output", type=Path, default=ROOT / ".runtime" / "device-benchmark.json")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if not 1 <= args.repetitions <= 10:
        parser.error("Use between one and ten warm repetitions.")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.worker:
        if args.device == "both":
            parser.error("A worker requires a single device.")
        result = measure(args.device, args.repetitions)
    else:
        result = {"created_at": datetime.now(timezone.utc).isoformat(), "devices": {},
            "scope": "One real public-domain clip, repeated uncached alignment. No independent human validation; speed depends on hardware and load."}
        for device in ("cpu", "cuda") if args.device == "both" else (args.device,):
            destination = args.output.with_name(f"{args.output.stem}-{device}.json")
            print(f"Measuring {device} in an isolated process...", flush=True)
            subprocess.run([sys.executable, str(Path(__file__).resolve()), "--worker", "--device", device,
                "--repetitions", str(args.repetitions), "--output", str(destination)], cwd=ROOT, check=True)
            result["devices"][device] = json.loads(destination.read_text(encoding="utf-8"))
        if args.device == "both":
            cpu, gpu = result["devices"]["cpu"], result["devices"]["cuda"]
            left, right = cpu["alignment"], gpu["alignment"]
            same_words = [word["word"] for word in left["words"]] == [word["word"] for word in right["words"]]
            result["comparison"] = {
                "both_used_requested_backend": cpu["compute"]["device"] == "cpu" and gpu["compute"]["device"] == "cuda",
                "same_word_sequence": same_words,
                "same_greedy_transcription": left["recognized_text"] == right["recognized_text"],
                "maximum_word_boundary_difference_seconds": round(max(abs(a[edge] - b[edge])
                    for a, b in zip(left["words"], right["words"]) for edge in ("start", "end")), 4) if same_words else None,
                "maximum_word_confidence_difference": round(max(abs(a["score"] - b["score"])
                    for a, b in zip(left["words"], right["words"])), 4) if same_words else None,
                "warm_alignment_speedup": round(cpu["warm_median_seconds"] / gpu["warm_median_seconds"], 2)}
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False), encoding="utf-8")
    print(f"Saved {args.output}", flush=True)
    if "comparison" in result:
        print(json.dumps(result["comparison"], indent=2), flush=True)


if __name__ == "__main__":
    main()
