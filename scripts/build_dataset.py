"""Reproduce the public-domain excerpt benchmark and labelled audio edits.

Run from the project root with the project Python. Downloading is optional when
raw sources already exist. Transformation labels are never inference inputs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from urllib.request import Request, urlopen

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SEVERITIES = {
    "energy": [("mild", 5.0), ("moderate", 9.0), ("severe", 14.0)],
    "pauses": [("mild", 0.65), ("moderate", 1.1), ("severe", 1.8)],
    "pacing": [("mild", 1.35), ("moderate", 1.65), ("severe", 2.0)],
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def augment_audio(audio, sample_rate, words, flaw, amount, word_range):
    """Return changed audio, participant-time labels, and reproducible parameters.

    The inclusive word range defines energy/rate regions. For a pause, insert
    after its first word; label the complete modified inter-word gap. Round all
    operations to sample boundaries so labels exactly describe written samples.
    """
    audio = np.asarray(audio, dtype=np.float32)
    if flaw == "clean":
        return audio.copy(), [], {"operation": "identity"}
    lo, hi = word_range
    if not (0 <= lo <= hi < len(words)):
        raise ValueError("Invalid word range")
    begin = round(float(words[lo]["start"]) * sample_rate)
    end = round(float(words[hi]["end"]) * sample_rate)
    if not (0 <= begin < end <= len(audio)) or amount <= 0:
        raise ValueError("Invalid audio edit boundaries or amount")
    common = {"word_range": [lo, hi], "reference_start": begin / sample_rate,
              "reference_end": end / sample_rate}
    if flaw == "energy":
        output = audio.copy()
        gain = float(10 ** (-amount / 20))
        envelope = np.full(end - begin, gain, dtype=np.float32)
        ramp = min(round(0.01 * sample_rate), len(envelope) // 4)
        if ramp:
            envelope[:ramp] = np.linspace(1, gain, ramp)
            envelope[-ramp:] = np.linspace(gain, 1, ramp)
        output[begin:end] *= envelope
        label = {"type": flaw, "start": begin / sample_rate, "end": end / sample_rate}
        return output, [label], {**common, "operation": "local_gain", "reduction_db": amount, "ramp_seconds": ramp / sample_rate}
    if flaw == "pauses":
        if lo + 1 >= len(words):
            raise ValueError("Pause insertion requires a following word")
        gap_start = round(float(words[lo]["end"]) * sample_rate)
        gap_end = round(float(words[lo + 1]["start"]) * sample_rate)
        if gap_end < gap_start:
            raise ValueError("Aligned word intervals overlap")
        insertion = (gap_start + gap_end) // 2
        count = round(amount * sample_rate)
        output = np.concatenate([audio[:insertion], np.zeros(count, np.float32), audio[insertion:]])
        label = {"type": flaw, "start": gap_start / sample_rate, "end": (gap_end + count) / sample_rate}
        return output, [label], {**common, "operation": "insert_silence", "inserted_seconds": count / sample_rate,
                                "insertion_seconds": insertion / sample_rate}
    if flaw == "pacing":
        import librosa
        segment = librosa.effects.time_stretch(audio[begin:end], rate=float(amount))
        output = np.concatenate([audio[:begin], segment, audio[end:]]).astype(np.float32)
        label = {"type": flaw, "start": begin / sample_rate, "end": (begin + len(segment)) / sample_rate}
        return output, [label], {**common, "operation": "phase_vocoder_time_stretch", "rate": amount,
                                "pitch_preserving": True, "output_segment_samples": len(segment)}
    raise ValueError(f"Unknown flaw: {flaw}")


def download_source(source: dict) -> Path:
    path = ROOT / source["local_file"]
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        print(f"Downloading {source['id']}...", flush=True)
        request = Request(source["download_url"], headers={"User-Agent": "SpeakTrace educational prototype/1.0"})
        temp = path.with_suffix(path.suffix + ".part")
        with urlopen(request, timeout=120) as response, temp.open("wb") as handle:
            while block := response.read(1024 * 1024):
                handle.write(block)
        temp.replace(path)
    if sha256(path) != source["sha256"]:
        raise ValueError(f"Source checksum mismatch: {path}")
    return path


def write_variants(reference, audio, words, sample_rate, root=ROOT):
    import soundfile as sf
    variants = []
    lo = max(1, len(words) // 3)
    plans = [("clean", "control", 0)] + [(flaw, severity, amount) for flaw, levels in SEVERITIES.items() for severity, amount in levels]
    for flaw, severity, amount in plans:
        hi = min(len(words) - 2, lo + (9 if flaw == "pacing" else 5))
        changed, labels, transform = augment_audio(audio, sample_rate, words, flaw, amount, (lo, hi))
        variant_id = "clean" if flaw == "clean" else f"{flaw}-{severity}"
        vpath = root / f"data/variants/{reference['id']}/{variant_id}.wav"
        vpath.parent.mkdir(parents=True, exist_ok=True)
        sf.write(vpath, changed, sample_rate, subtype="PCM_16")
        variants.append({"id": variant_id, "label": "Original clean control" if flaw == "clean" else f"Generated {severity} {flaw}",
                         "flaw": flaw, "severity": severity, "synthetic": flaw != "clean",
                         "audio": vpath.relative_to(root).as_posix(), "sha256": sha256(vpath),
                         "duration": len(changed) / sample_rate, "labels": labels, "transform": transform})
    return variants


def regenerate_variants(root=ROOT):
    """Offline reconstruction from bundled WAVs and genuine CTC annotations.

    No source acquisition or model inference occurs here. These annotations
    are allowed generator inputs; the detector never consumes them.
    """
    import soundfile as sf
    root = Path(root)
    manifest_path = root / "data/manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for reference in manifest["references"]:
        path = root / reference["audio"]
        if reference.get("sha256") and sha256(path) != reference["sha256"]:
            raise ValueError(f"Reference checksum mismatch: {reference['id']}")
        annotation_path = root / f"data/annotations/{reference['id']}.json"
        if not annotation_path.exists():
            raise FileNotFoundError(f"Bundled generator annotation missing: {annotation_path}. Run the full builder after installing the model.")
        annotation = json.loads(annotation_path.read_text(encoding="utf-8"))
        audio, sample_rate = sf.read(path, dtype="float32")
        reference["variants"] = write_variants(reference, audio, annotation["words"], sample_rate, root)
        print(f"Regenerated {reference['id']}: {len(reference['variants'])} variants offline", flush=True)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--references-only", action="store_true", help="Cut and validate references without making variants")
    mode.add_argument("--variants-only", action="store_true", help="Offline: rebuild variants from bundled references and generator annotations, without raw sources or model inference")
    parser.add_argument("--skip-download", action="store_true", help="Require existing sources")
    args = parser.parse_args()
    if args.variants_only:
        regenerate_variants()
        return
    import soundfile as sf
    from scipy.signal import resample_poly
    from math import gcd
    from speaktrace.alignment import align_audio

    sources = json.loads((ROOT / "data/sources.json").read_text(encoding="utf-8"))
    excerpts = json.loads((ROOT / "data/excerpts.json").read_text(encoding="utf-8"))
    decoded = {}
    source_map = {source["id"]: source for source in sources}
    for source in sources:
        path = ROOT / source["local_file"]
        if args.skip_download and not path.exists():
            raise FileNotFoundError(path)
        path = download_source(source)
        audio, sr = sf.read(path, dtype="float32", always_2d=True)
        audio = audio.mean(axis=1)
        if sr != 16000:
            factor = gcd(sr, 16000)
            audio = resample_poly(audio, 16000 // factor, sr // factor).astype(np.float32)
        decoded[source["id"]] = audio

    references = []
    for excerpt in excerpts:
        source = source_map[excerpt["source_group"]]
        start, end = excerpt["source_offset_seconds"], excerpt["source_end_seconds"]
        audio = decoded[source["id"]][round(start * 16000):round(end * 16000)]
        path = ROOT / f"data/references/{excerpt['id']}.wav"
        path.parent.mkdir(parents=True, exist_ok=True)
        sf.write(path, audio, 16000, subtype="PCM_16")
        # Align the actual quantized deliverable, not a pre-encoding waveform.
        audio, _ = sf.read(path, dtype="float32")
        alignment = align_audio(audio, 16000, excerpt["transcript"])
        if alignment["coverage"] < 0.9 or alignment["transcript_agreement"] < 0.75:
            quality = {k: alignment[k] for k in ("confidence", "coverage", "transcript_agreement")}
            raise ValueError(f"Reference alignment unreliable: {excerpt['id']}: {quality}")
        meta = {**excerpt, "source_url": source["source_url"], "transcript_url": source["transcript_url"],
                "download_url": source["download_url"], "license": source["license"],
                "license_url": source["license_url"], "duration": len(audio) / 16000,
                "audio": path.relative_to(ROOT).as_posix(), "sha256": sha256(path),
                "alignment_validation": {k: alignment[k] for k in ("confidence", "coverage", "transcript_agreement", "recognized_text")},
                "synthetic": False}
        path.with_suffix(".json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
        annotation = ROOT / f"data/annotations/{excerpt['id']}.json"
        annotation.parent.mkdir(parents=True, exist_ok=True)
        annotation.write_text(json.dumps({"purpose": "Generator region selection only; never inference input", **alignment}, indent=2) + "\n", encoding="utf-8")
        variants = []
        if not args.references_only:
            variants = write_variants(meta, audio, alignment["words"], 16000)
        references.append({**meta, "variants": variants})
        print(f"Prepared {excerpt['id']}: {len(audio)/16000:.2f}s, {len(variants)} variants", flush=True)
    manifest = {"version": "1.0.0", "sample_rate": 16000,
                "description": "Real public-domain archive excerpts; isolated generated delivery changes.",
                "generator": "scripts/build_dataset.py", "references": references}
    (ROOT / "data/manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
