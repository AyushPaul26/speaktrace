"""Measure complete CPU analysis in isolated Linux/Vercel build processes.

This is a build-time resource probe, never a benchmark of speech accuracy. It
uses the already downloaded pinned model and included public-domain recordings.
It performs no network calls, package installation, or local model downloads.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time


ROOT = Path(__file__).resolve().parents[1]
CASES = ("real-pair", "30s-stress-pair")
PREFIX = "SPEAKTRACE_MEMORY_WORKER "


def fits_limits(result: dict, memory_mib: float, seconds: float) -> dict:
    """Fail closed for failed/missing/nonfinite measurements or wrong devices."""
    import math

    def within(value, maximum):
        return (isinstance(value, (int, float)) and not isinstance(value, bool)
                and math.isfinite(value) and 0 < value <= maximum)

    return {
        "completed": result.get("status") == "complete",
        "cpu_only": result.get("device") == "cpu",
        "uncached": result.get("cached_alignment") is False,
        "memory_fits": within(result.get("peak_rss_mib"), memory_mib),
        "duration_fits": within(result.get("cold_total_seconds"), seconds),
    }


def measure(case: str) -> dict:
    import resource

    started = time.perf_counter()
    os.environ.update(SPEAKTRACE_DEVICE="cpu", OMP_NUM_THREADS="1",
                      MKL_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1",
                      HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1",
                      HF_HUB_DISABLE_TELEMETRY="1", TOKENIZERS_PARALLELISM="false")
    sys.path.insert(0, str(ROOT))
    import numpy as np
    import torch
    from speaktrace.alignment import _load_model
    from speaktrace.audio import decode_audio
    from speaktrace.pipeline import run_analysis

    torch.set_num_interop_threads(1)
    manifest = json.loads((ROOT / "data/manifest.json").read_text(encoding="utf-8"))
    reference = next(item for item in manifest["references"] if item["id"] == "reagan-families")
    control = next(item for item in reference["variants"] if item["flaw"] == "clean")
    reference_audio, rate = decode_audio(ROOT / reference["audio"])
    participant_audio, participant_rate = decode_audio(ROOT / control["audio"])
    if rate != participant_rate or rate != 16000:
        raise RuntimeError("Probe expects the same 16 kHz decoding as production.")
    if case == "30s-stress-pair":
        # The original transcript intentionally does not describe the tiled clip.
        # This exercises full-size inference/features; resulting scores are ignored.
        samples = 30 * rate
        reference_audio = np.tile(reference_audio, int(np.ceil(samples / len(reference_audio))))[:samples]
        participant_audio = reference_audio.copy()

    # The production loader currently chooses up to four threads. Override only
    # after loading, so measured inference matches Hobby's one-vCPU configuration.
    _load_model()
    torch.set_num_threads(1)
    ready = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="speaktrace-hosted-probe-") as directory:
        result = run_analysis("0" * 32, Path(directory), lambda *_: None,
            reference_audio=reference_audio, participant_audio=participant_audio,
            transcript=reference["transcript"], reference_name="Public reference",
            participant_name="Public control", title="Hosted resource probe",
            mode="upload")
        # Include response serialization in the observed process peak.
        response_bytes = len(json.dumps(result, ensure_ascii=False, allow_nan=False).encode("utf-8"))
    elapsed = time.perf_counter() - started
    return {
        "case": case, "status": "complete",
        "scope": ("Real public-domain reference and its unchanged control; full analysis."
                  if case == "real-pair" else
                  "Two 30-second tiled clips at the hosted duration limit; full-pipeline resource stress only, not accuracy validation."),
        "source": reference["id"],
        "audio_seconds": [round(len(reference_audio) / rate, 4), round(len(participant_audio) / rate, 4)],
        "torch_version": str(torch.__version__), "torch_cuda_version": torch.version.cuda,
        "torch_threads": torch.get_num_threads(), "device": result["compute"]["device"],
        "cached_alignment": result["compute"]["cached_alignment"],
        "peak_rss_mib": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 3),
        "imports_and_model_load_seconds": round(ready - started, 3),
        "pipeline_and_serialization_seconds": round(time.perf_counter() - ready, 3),
        "cold_total_seconds": round(elapsed, 3), "result_bytes": response_bytes,
    }


def run_worker(case: str, timeout: float) -> dict:
    command = [sys.executable, str(Path(__file__).resolve()), "--worker", case]
    started = time.perf_counter()
    try:
        process = subprocess.run(command, cwd=ROOT, capture_output=True, text=True,
                                 encoding="utf-8", errors="replace", timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"case": case, "status": "error", "error": "Worker exceeded the wall-time limit.",
                "cold_total_seconds": round(time.perf_counter() - started, 3)}
    rows = [line[len(PREFIX):] for line in process.stdout.splitlines() if line.startswith(PREFIX)]
    try:
        result = json.loads(rows[-1]) if rows else None
    except (ValueError, IndexError):
        result = None
    if process.returncode or not isinstance(result, dict):
        return {"case": case, "status": "error", "exit_code": process.returncode,
                "error": "Resource probe worker failed.", "stderr_tail": process.stderr[-2000:]}
    # Include subprocess startup/teardown in the conservative function-duration gate.
    result["worker_wall_seconds"] = round(time.perf_counter() - started, 3)
    result["cold_total_seconds"] = max(result["cold_total_seconds"], result["worker_wall_seconds"])
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-memory-mib", type=float, default=1900,
                        help="Peak RSS ceiling; default leaves headroom under Hobby's 2 GB.")
    parser.add_argument("--max-seconds", type=float, default=300,
                        help="Maximum cold worker lifetime, including imports and model loading.")
    parser.add_argument("--output", type=Path, default=ROOT / "reports/hosted-memory-build.json")
    parser.add_argument("--worker", choices=CASES, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if sys.platform != "linux" or os.environ.get("VERCEL") != "1":
        parser.error("Run this probe only in a Linux Vercel build after model setup; it will not run locally.")
    if not 0 < args.max_memory_mib <= 1900 or not 0 < args.max_seconds <= 300:
        parser.error("Limits must be positive and no higher than 1900 MiB / 300 seconds.")
    if args.worker:
        try:
            result = measure(args.worker)
        except Exception as error:
            print(PREFIX + json.dumps({"case": args.worker, "status": "error",
                                       "error": f"{type(error).__name__}: {error}"}), flush=True)
            raise
        print(PREFIX + json.dumps(result, allow_nan=False, separators=(",", ":")), flush=True)
        return 0

    measurements = []
    for case in CASES:
        result = run_worker(case, args.max_seconds)
        result["checks"] = fits_limits(result, args.max_memory_mib, args.max_seconds)
        result["passed"] = all(result["checks"].values())
        measurements.append(result)
        print("SPEAKTRACE_HOSTED_PROBE " + json.dumps(result, allow_nan=False, separators=(",", ":")), flush=True)
    report = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "platform": sys.platform, "python": sys.version.split()[0],
        "limits": {"peak_rss_mib": args.max_memory_mib, "cold_seconds": args.max_seconds},
        "scope": "Isolated full-pipeline CPU workers. Build-host timings are not runtime latency guarantees.",
        "measurements": measurements, "passed": all(item["passed"] for item in measurements),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    print("SPEAKTRACE_HOSTED_PROBE_SUMMARY " + json.dumps(report, allow_nan=False, separators=(",", ":")), flush=True)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
