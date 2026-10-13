"""Run real local inference on source-disjoint archive perturbation controls.

Default execution recomputes every alignment. --use-cache is explicit and keys
alignments by audio hash, transcript, model identity and alignment code hash.
Labels are only read after comparison, in event matching below.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def interval_iou(a, b):
    intersection = max(0.0, min(a["end"], b["end"]) - max(a["start"], b["start"]))
    union = max(a["end"], b["end"]) - min(a["start"], b["start"])
    return intersection / union if union > 0 else 0.0


def match_events(labels, findings, threshold=0.3):
    """Maximum-cardinality same-type matching, then maximum total IoU.

    Precision includes wrong-type and duplicate events as false positives.
    Mean absolute boundary error is averaged over start/end, then matches.
    """
    import numpy as np
    from scipy.optimize import linear_sum_assignment
    rows, cols = len(labels), len(findings)
    matched = []
    if rows and cols:
        ious = np.zeros((rows, cols))
        for i, label in enumerate(labels):
            for j, finding in enumerate(findings):
                if label["type"] == finding["type"]:
                    ious[i, j] = interval_iou(label, finding)
        eligible = ious >= threshold
        # Cardinality dominates total IoU even when there are multiple labels.
        benefit = eligible * (1 + min(rows, cols) + ious)
        ri, ci = linear_sum_assignment(benefit, maximize=True)
        matched = [(int(i), int(j), float(ious[i, j])) for i, j in zip(ri, ci) if eligible[i, j]]
    errors = [(abs(labels[i]["start"] - findings[j]["start"]) + abs(labels[i]["end"] - findings[j]["end"])) / 2 for i, j, _ in matched]
    return {"tp": len(matched), "fp": cols - len(matched), "fn": rows - len(matched),
            "matched_ious": [v for _, _, v in matched], "boundary_errors_seconds": errors}


def validate_source_splits(references):
    groups = defaultdict(set)
    for ref in references:
        groups[ref["source_group"]].add(ref["split"])
    if any(len(splits) > 1 for splits in groups.values()):
        raise ValueError("A source group occurs in multiple splits; evaluation would leak source families")
    return dict(groups)


def aggregate(rows, flaw=None):
    def relevant(row):
        if flaw is None:
            return row["matching"]
        return match_events([v for v in row["labels"] if v["type"] == flaw],
                            [v for v in row["findings"] if v["type"] == flaw])
    metrics = [relevant(row) for row in rows]
    tp, fp, fn = (sum(m[key] for m in metrics) for key in ("tp", "fp", "fn"))
    ious = [v for m in metrics for v in m["matched_ious"]]
    boundaries = [v for m in metrics for v in m["boundary_errors_seconds"]]
    clean = [row for row in rows if row["flaw"] == "clean"]
    clean_bad = sum(any(flaw is None or finding["type"] == flaw for finding in row["findings"]) for row in clean)
    return {"examples": len(rows), "tp": tp, "fp": fp, "fn": fn,
            "event_precision": tp / (tp + fp) if tp + fp else None,
            "event_recall": tp / (tp + fn) if tp + fn else None,
            "event_f1": 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None,
            "matched_mean_iou": sum(ious) / len(ious) if ious else None,
            "matched_boundary_mae_seconds": sum(boundaries) / len(boundaries) if boundaries else None,
            "clean_controls": len(clean), "clean_controls_with_flags": clean_bad,
            "clean_control_false_positive_rate": clean_bad / len(clean) if clean else None,
            "withheld_or_failed": sum(row["status"] != "complete" for row in rows)}


def severity_ordering(rows):
    groups = defaultdict(dict)
    for row in rows:
        if row["flaw"] != "clean":
            groups[(row["reference_id"], row["flaw"])][row["severity"]] = row["score"]
    triples = []
    for (reference_id, flaw), values in groups.items():
        scores = [values.get(s) for s in ("mild", "moderate", "severe")]
        available = all(value is not None for value in scores)
        triples.append({"reference_id": reference_id, "flaw": flaw, "scores_mild_to_severe": scores,
                        "available": available, "nonincreasing": bool(available and scores[0] >= scores[1] >= scores[2]),
                        "strictly_decreasing": bool(available and scores[0] > scores[1] > scores[2])})
    available = [row for row in triples if row["available"]]
    return {"triples": len(triples), "scorable_triples": len(available),
            "nonincreasing_count": sum(row["nonincreasing"] for row in available),
            "strictly_decreasing_count": sum(row["strictly_decreasing"] for row in available), "details": triples}


def run_evaluation(use_cache=False, split=None):
    import soundfile as sf
    from speaktrace import alignment as alignment_module
    from speaktrace.alignment import align_audio, runtime_metadata
    from speaktrace.core.comparison import compare_recordings, rubric_metadata
    from speaktrace.pipeline import apply_alignment_policy

    manifest = json.loads((ROOT / "data/manifest.json").read_text(encoding="utf-8"))
    groups = validate_source_splits(manifest["references"])
    code_hash = hashlib.sha256(Path(alignment_module.__file__).read_bytes()).hexdigest()
    model = getattr(alignment_module, "MODEL_ID", "facebook/wav2vec2-base-960h")
    revision = alignment_module.model_revision()
    cache_dir = ROOT / ".runtime/evaluation-alignments"
    hits = 0
    calls = 0
    alignment_devices = defaultdict(int)

    def aligned(path, audio, sr, transcript):
        nonlocal hits, calls
        key_input = {"audio_sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "transcript": transcript,
                     "model": str(model), "revision": str(revision), "alignment_code_sha256": code_hash,
                     "compute": {k: runtime_metadata().get(k) for k in ("requested_device", "device", "device_name", "precision", "torch_version", "cuda_version")}}
        key = hashlib.sha256(json.dumps(key_input, sort_keys=True).encode()).hexdigest()
        cache_path = cache_dir / f"{key}.json"
        if use_cache and cache_path.exists():
            hits += 1
            result = json.loads(cache_path.read_text(encoding="utf-8"))["alignment"]
            result["cached"] = True
            alignment_devices[result.get("compute", {}).get("device", "unknown")] += 1
            return result
        calls += 1
        result = align_audio(audio, sr, transcript, use_cache=False)
        alignment_devices[result.get("compute", {}).get("device", "unknown")] += 1
        # A CUDA out-of-memory retry can produce CPU output. Store it under
        # the device actually used, rather than the pre-inference GPU key.
        key_input["compute"] = {k: result.get("compute", {}).get(k) for k in
                                ("requested_device", "device", "device_name", "precision", "torch_version", "cuda_version")}
        key = hashlib.sha256(json.dumps(key_input, sort_keys=True).encode()).hexdigest()
        cache_path = cache_dir / f"{key}.json"
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps({"key": key_input, "alignment": result}) + "\n", encoding="utf-8")
        return result

    rows = []
    started = time.perf_counter()
    for reference in manifest["references"]:
        if split and reference["split"] != split:
            continue
        reference_path = ROOT / reference["audio"]
        reference_audio, sr = sf.read(reference_path, dtype="float32")
        reference_alignment = aligned(reference_path, reference_audio, sr, reference["transcript"])
        for variant in reference["variants"]:
            print(f"Evaluating {reference['id']}/{variant['id']}", flush=True)
            tick = time.perf_counter()
            base = {"reference_id": reference["id"], "variant_id": variant["id"],
                    "source_group": reference["source_group"], "split": reference["split"],
                    "flaw": variant["flaw"], "severity": variant["severity"]}
            try:
                participant_path = ROOT / variant["audio"]
                participant_audio, participant_sr = sf.read(participant_path, dtype="float32")
                if participant_sr != sr:
                    raise ValueError("Dataset files have inconsistent sample rates")
                participant_alignment = aligned(participant_path, participant_audio, sr, reference["transcript"])
                # No labels, transforms, severity, IDs, or expected boundaries enter inference.
                result = compare_recordings(reference_audio, participant_audio, sr,
                                            reference_alignment["words"], participant_alignment["words"], reference["transcript"])
                result = apply_alignment_policy(result, reference_alignment, participant_alignment)
                finding_keys = ("type", "start", "end", "severity", "severity_value")
                findings = [{k: finding[k] for k in finding_keys if k in finding} for finding in result["findings"]]
                row = {**base, "status": result["summary"]["status"], "score": result["summary"]["score"],
                       "findings": findings, "alignment_confidence": participant_alignment["confidence"],
                       "transcript_agreement": participant_alignment["transcript_agreement"], "warnings": result["warnings"],
                       "compute": {"reference": reference_alignment.get("compute", {}), "participant": participant_alignment.get("compute", {})}}
                row["alignment_cached"] = {"reference": bool(reference_alignment.get("cached")),
                                           "participant": bool(participant_alignment.get("cached"))}
            except Exception as exc:
                row = {**base, "status": "error", "score": None, "findings": [], "error": f"{type(exc).__name__}: {exc}"}
            row["labels"] = variant["labels"]
            row["matching"] = match_events(row["labels"], row["findings"])
            row["seconds"] = round(time.perf_counter() - tick, 3)
            rows.append(row)
    report = {
        "version": "1.0.0", "generated_at": datetime.now(timezone.utc).isoformat(),
        "dataset_version": manifest["version"], "manifest_sha256": hashlib.sha256((ROOT / "data/manifest.json").read_bytes()).hexdigest(),
        "model": str(model), "model_revision": str(revision), "alignment_code_sha256": code_hash,
        "rubric": rubric_metadata(),
        "comparison_code_sha256": hashlib.sha256((ROOT / "speaktrace/core/comparison.py").read_bytes()).hexdigest(),
        "alignment_policy_code_sha256": hashlib.sha256((ROOT / "speaktrace/pipeline.py").read_bytes()).hexdigest(),
        "device": next(iter(alignment_devices)) if len(alignment_devices) == 1 else "mixed",
        "compute": runtime_metadata(), "alignment_devices": dict(alignment_devices),
        "cache_requested": use_cache, "alignment_cache_hits": hits,
        "fresh_alignment_calls": calls, "elapsed_seconds": round(time.perf_counter() - started, 3),
        "matching": "Maximum-cardinality one-to-one same-type event matching at interval IoU >= 0.30; unmatched detections are FP, unmatched labels are FN.",
        "source_splits": {group: sorted(splits) for group, splits in groups.items()},
        "splits": {name: {"overall": aggregate([r for r in rows if r["split"] == name]),
                          "by_flaw": {flaw: aggregate([r for r in rows if r["split"] == name], flaw) for flaw in ("pacing", "pauses", "energy")},
                          "severity_ordering": severity_ordering([r for r in rows if r["split"] == name])} for name in sorted({r["split"] for r in rows})},
        "limitations": ["Synthetic perturbation benchmark, not independent human-delivery validation.",
                        "Only two male US presidential speakers and two archive recording conditions; results do not estimate population performance.",
                        "Reference word boundaries used to place edits are model estimates, not human-annotated word timestamps.",
                        "Ground-truth spans describe actual waveform operations; detector phrase windows need not exactly coincide.",
                        "Human perceptual quality and usefulness remain unvalidated."],
        "examples": rows,
    }
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--use-cache", action="store_true")
    parser.add_argument("--split", choices=["dev", "test"])
    parser.add_argument("--output", type=Path, default=ROOT / "reports/evaluation.json")
    args = parser.parse_args()
    report = run_evaluation(args.use_cache, args.split)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "splits": report["splits"], "elapsed_seconds": report["elapsed_seconds"]}, indent=2))


if __name__ == "__main__":
    main()
