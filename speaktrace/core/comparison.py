"""Versioned reference-relative speech rubric, independent of dataset labels.

The score describes similarity under three explicit heuristics. It is not a
universal measure of speaking skill, emotion, confidence, or intelligibility.
Raw CTC word probabilities are heuristic alignment-quality signals, not
calibrated probabilities that an assessment is correct.
"""
import math
from numbers import Real

import numpy as np

from ..alignment import normalize_transcript
from .features import validate_audio


RUBRIC_VERSION = "reference-relative-1.1.0"
DEFAULT_WEIGHTS = {"pacing": 40.0, "pauses": 35.0, "energy": 25.0}
THRESHOLDS = {
    "min_word_quality": .35,
    "min_region_quality": .55,
    "min_recording_quality": .55,
    "min_reliable_word_fraction": .70,
    "min_assessed_word_fraction": .50,
    "min_clip_seconds": 2.0,
    "min_word_power_relative_to_peak": 1e-12,
    "min_region_words": 5,
    "max_region_words": 8,
    "target_region_words": 6,
    "rush_ratio": 1.25,
    "rush_min_seconds_saved": .25,
    "pause_extra_seconds": .30,
    "pause_min_seconds": .35,
    "pause_ratio": 1.8,
    "pause_reference_floor_seconds": .12,
    "pause_misplaced_reference_seconds": .18,
    "pause_quiet_below_word_median_db": 25.0,
    "pause_max_uncertain_words": 2,
    "pause_context_words_each_side": 2,
    "energy_drop_db": 5.0,
}


def normalize_weights(weights: dict | None) -> dict:
    if weights is None:
        weights = DEFAULT_WEIGHTS
    if not isinstance(weights, dict) or set(weights) != set(DEFAULT_WEIGHTS):
        raise ValueError("Weights must include exactly pacing, pauses, and energy.")
    if any(isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(value) or value < 0 for value in weights.values()):
        raise ValueError("Weights must be finite, nonnegative numbers.")
    # Scaling before summing also handles valid very large finite weights.
    maximum = max(weights.values())
    if maximum <= 0:
        raise ValueError("At least one weight must be greater than zero.")
    scaled = {key: float(weights[key] / maximum) for key in DEFAULT_WEIGHTS}
    total = sum(scaled.values())
    return {key: value / total for key, value in scaled.items()}


def rubric_metadata() -> dict:
    """Return independent JSON-safe defaults for the methodology endpoint."""
    return {"version": RUBRIC_VERSION, "weights": normalize_weights(None), "thresholds": dict(THRESHOLDS)}


def _tokens(text: str) -> list[str]:
    return [word.lower() for word in normalize_transcript(text)]


def _validate_words(words: list[dict], duration: float, tokens: list[str], name: str) -> list[dict]:
    if not isinstance(words, list) or not words or len(words) != len(tokens):
        raise ValueError(f"{name} alignment must contain every transcript word in order.")
    result = []
    previous_end = 0.0
    for index, word in enumerate(words):
        if not isinstance(word, dict) or not isinstance(word.get("word"), str) or _tokens(word["word"]) != [tokens[index]]:
            raise ValueError(f"{name} alignment does not match transcript word {index + 1}.")
        values = [word.get(key) for key in ("start", "end", "score")]
        if any(isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(value) for value in values):
            raise ValueError(f"{name} word {index + 1} needs finite start, end, and score values.")
        start, end, score = map(float, values)
        if start < 0 or start < previous_end - 1e-6 or end <= start or end > duration + 1e-4 or not 0 <= score <= 1:
            raise ValueError(f"{name} word {index + 1} has invalid times or alignment quality.")
        result.append({"word": tokens[index], "start": start, "end": end, "score": score})
        previous_end = end
    return result


def _regions(count: int) -> list[list[int]]:
    """Balanced nonoverlapping ~6-word windows; nine words leave one unscored.

    Window boundaries depend only on transcript length, never audio or labels.
    Five to eight words provide a stable local comparison without one-word WPM.
    """
    if count < 5:
        return []
    if count <= 8:
        return [list(range(count))]
    if count == 9:
        return [list(range(8))]
    number = max(2, round(count / 6))
    while count // number < 5:
        number -= 1
    while math.ceil(count / number) > 8:
        number += 1
    size, remainder = divmod(count, number)
    regions, start = [], 0
    for index in range(number):
        end = start + size + (index < remainder)
        regions.append(list(range(start, end)))
        start = end
    return regions


def _word_energy(audio: np.ndarray, sample_rate: int, words: list[dict]) -> tuple[np.ndarray, np.ndarray]:
    normalized = audio / np.max(np.abs(audio))
    power = []
    for word in words:
        start, end = round(word["start"] * sample_rate), round(word["end"] * sample_rate)
        if end <= start:
            raise ValueError("An aligned word is shorter than one audio sample.")
        segment = normalized[start:end]
        power.append(float(np.mean((segment - np.mean(segment)) ** 2)))
    db = 10 * np.log10(np.maximum(power, 1e-20))
    active = np.asarray(power) > THRESHOLDS["min_word_power_relative_to_peak"]
    return db, active


def _severity(value: float) -> tuple[str, float]:
    value = round(float(np.clip(value, 0, 1)), 5)
    return ("severe" if value >= .75 else "moderate" if value >= .4 else "mild", value)


def _longest_quiet(audio: np.ndarray, sample_rate: int, start: float, end: float, baseline_db: float) -> tuple[float, float, float]:
    """Locate continuous quiet audio independently of uncertain word boundaries.

    A 20 ms frame must be at least 25 dB below the reliable-word median.
    The 10 ms hop bounds edge uncertainty; active/noisy audio is not a pause.
    """
    first, last = round(start * sample_rate), round(end * sample_rate)
    segment = audio[first:last] / np.max(np.abs(audio))
    width, hop = max(2, round(.02 * sample_rate)), max(1, round(.01 * sample_rate))
    if len(segment) < width:
        return start, start, 0.0
    frames = np.lib.stride_tricks.sliding_window_view(segment, width)[::hop]
    centered = frames - frames.mean(axis=1, keepdims=True)
    power = np.mean(centered * centered, axis=1)
    limit = 10 ** ((baseline_db - THRESHOLDS["pause_quiet_below_word_median_db"]) / 10)
    quiet = power <= limit
    edges = np.diff(np.r_[False, quiet, False].astype(int))
    beginnings, endings = np.flatnonzero(edges == 1), np.flatnonzero(edges == -1)
    if not len(beginnings):
        return start, start, 0.0
    longest = int(np.argmax(endings - beginnings))
    quiet_start = (first + beginnings[longest] * hop) / sample_rate
    quiet_end = (first + (endings[longest] - 1) * hop + width) / sample_rate
    return float(quiet_start), float(quiet_end), float(quiet_end - quiet_start)


def _uncertain_intervals(good: np.ndarray, quality: np.ndarray) -> list[tuple[int, int, list[int]]]:
    """Bridge only short uncertain runs with strong context on both sides."""
    reliable_indices = np.flatnonzero(good).tolist()
    intervals = []
    width = THRESHOLDS["pause_context_words_each_side"]
    for left, right in zip(reliable_indices[:-1], reliable_indices[1:]):
        if not 1 <= right - left - 1 <= THRESHOLDS["pause_max_uncertain_words"]:
            continue
        if left - width + 1 < 0 or right + width > len(good):
            continue
        context = list(range(left - width + 1, left + 1)) + list(range(right, right + width))
        if np.all(good[context]) and np.all(quality[context] >= THRESHOLDS["min_region_quality"]):
            intervals.append((left, right, context))
    return intervals


def _finding(kind, title, indices, ref, part, confidence, amount, explanation, advice, measurement, reference_value, participant_value, unit, gap=False):
    start = part[indices[0]]["end" if gap else "start"]
    end = part[indices[-1]]["start" if gap else "end"]
    reference_start = ref[indices[0]]["end" if gap else "start"]
    reference_end = ref[indices[-1]]["start" if gap else "end"]
    severity, value = _severity(amount)
    return {
        "id": f"{kind}-{indices[0]}-{indices[-1]}", "type": kind, "title": title,
        "start": round(start, 5), "end": round(end, 5),
        "reference_start": round(reference_start, 5), "reference_end": round(reference_end, 5),
        "severity": severity, "severity_value": value, "word_indices": indices,
        "explanation": explanation, "advice": advice, "confidence": round(confidence, 4),
        "evidence": {"measurement": measurement, "reference": round(reference_value, 4), "participant": round(participant_value, 4), "unit": unit},
    }


def compare_recordings(reference_audio: np.ndarray, participant_audio: np.ndarray, sample_rate: int, reference_words: list[dict], participant_words: list[dict], transcript: str, weights: dict | None = None) -> dict:
    """Compare aligned readings, withholding untrustworthy global/local scores.

    Pacing sums word durations, excluding every between-word gap. Energy is
    each region's mean word-RMS dB relative to its recording's reliable-word
    median. This resists constant gain and leading/trailing silence. Pauses are
    compared at the same transcript boundary, not at the same elapsed second.
    """
    normalized_weights = normalize_weights(weights)
    ref_audio = validate_audio(reference_audio, sample_rate)
    part_audio = validate_audio(participant_audio, sample_rate)
    if not np.any(ref_audio) or not np.any(part_audio):
        raise ValueError("Both recordings must contain non-silent audio.")
    if any(np.ptp(audio / np.max(np.abs(audio))) <= 1e-12 for audio in (ref_audio, part_audio)):
        raise ValueError("A constant signal is not measurable speech audio.")
    if not isinstance(transcript, str) or not _tokens(transcript):
        raise ValueError("A nonempty spoken-word transcript is required.")
    tokens = _tokens(transcript)
    ref = _validate_words(reference_words, len(ref_audio) / sample_rate, tokens, "Reference")
    part = _validate_words(participant_words, len(part_audio) / sample_rate, tokens, "Participant")
    quality = np.minimum([word["score"] for word in ref], [word["score"] for word in part])
    ref_energy, ref_active = _word_energy(ref_audio, sample_rate, ref)
    part_energy, part_active = _word_energy(part_audio, sample_rate, part)
    good = (quality >= THRESHOLDS["min_word_quality"]) & ref_active & part_active
    ref_baseline = part_baseline = 0.0
    if np.any(good):
        ref_baseline = float(np.median(ref_energy[good]))
        part_baseline = float(np.median(part_energy[good]))
        ref_energy -= ref_baseline
        part_energy -= part_baseline
    regions = _regions(len(tokens))
    eligible = [indices for indices in regions if np.all(good[indices]) and np.mean(quality[indices]) >= THRESHOLDS["min_region_quality"]]
    assessed = sum(map(len, eligible))
    confidence = float(np.mean(quality))
    warnings = []
    if len(eligible) < len(regions):
        warnings.append(f"Skipped {len(regions) - len(eligible)} phrase region(s) with weak alignment or no measurable word audio. Word probabilities are heuristic quality signals, not calibrated confidence.")
    if sum(map(len, regions)) < len(tokens):
        warnings.append("Too few words in a trailing fragment for a stable phrase comparison.")
    if assessed < len(tokens):
        warnings.append(f"Phrase scores cover {assessed} of {len(tokens)} words ({assessed / len(tokens):.0%}). Unassessed phrases may contain differences; a full score on the assessed words is not a full-recording match.")
    reliable = (
        min(ref[-1]["end"] - ref[0]["start"], part[-1]["end"] - part[0]["start"]) >= THRESHOLDS["min_clip_seconds"]
        and confidence >= THRESHOLDS["min_recording_quality"]
        and np.mean(good) >= THRESHOLDS["min_reliable_word_fraction"]
        and assessed >= 5 and assessed / len(tokens) >= THRESHOLDS["min_assessed_word_fraction"]
    )
    findings = []
    penalties = {key: 0.0 for key in DEFAULT_WEIGHTS}
    if reliable:
        for indices in eligible:
            region_quality = float(np.mean(quality[indices]))
            phrase = " ".join(tokens[index] for index in indices)
            ref_seconds = sum(ref[index]["end"] - ref[index]["start"] for index in indices)
            part_seconds = sum(part[index]["end"] - part[index]["start"] for index in indices)
            ratio = ref_seconds / part_seconds
            if ratio >= THRESHOLDS["rush_ratio"] and ref_seconds - part_seconds >= THRESHOLDS["rush_min_seconds_saved"]:
                reference_rate, participant_rate = 60 * len(indices) / ref_seconds, 60 * len(indices) / part_seconds
                finding = _finding("pacing", "Faster phrase than the reference", indices, ref, part, region_quality, (ratio - 1) / 1.2,
                    f'“{phrase}” has an articulation rate of {participant_rate:.0f} words/min versus {reference_rate:.0f} in the reference ({(ratio - 1) * 100:.0f}% faster). Between-word pauses are excluded.',
                    "Replay both phrases and try giving the words more time if you want to match the reference's rhythm.", "Articulation rate", reference_rate, participant_rate, "words/min")
                findings.append(finding)
                penalties["pacing"] += finding["severity_value"] * len(indices) / assessed
            ref_db, part_db = float(np.mean(ref_energy[indices])), float(np.mean(part_energy[indices]))
            drop = ref_db - part_db
            if drop >= THRESHOLDS["energy_drop_db"] - 1e-8:
                finding = _finding("energy", "Lower relative energy in this phrase", indices, ref, part, region_quality, drop / 18,
                    f'“{phrase}” is {drop:.1f} dB lower relative to its recording baseline: {part_db:+.1f} dB versus {ref_db:+.1f} dB in the reference. Overall microphone gain is removed.',
                    "Listen for a fading phrase ending or reduced emphasis. If intentional, keep it; otherwise repeat with steadier local energy.", "Word-RMS level relative to reliable-word median", ref_db, part_db, "dB")
                findings.append(finding)
                penalties["energy"] += finding["severity_value"] * len(indices) / assessed
        boundaries = [index for index in range(len(tokens) - 1) if np.all(good[index:index + 2]) and np.mean(quality[index:index + 2]) >= THRESHOLDS["min_region_quality"]]
        for index in boundaries:
            ref_gap = max(0.0, ref[index + 1]["start"] - ref[index]["end"])
            part_gap = max(0.0, part[index + 1]["start"] - part[index]["end"])
            extra = part_gap - ref_gap
            if extra >= THRESHOLDS["pause_extra_seconds"] and part_gap >= THRESHOLDS["pause_min_seconds"] and part_gap / max(ref_gap, THRESHOLDS["pause_reference_floor_seconds"]) >= THRESHOLDS["pause_ratio"]:
                misplaced = ref_gap < THRESHOLDS["pause_misplaced_reference_seconds"]
                finding = _finding("pauses", "Pause at a different place" if misplaced else "Longer pause than the reference", [index, index + 1], ref, part, float(np.mean(quality[index:index + 2])), extra / 1.5,
                    f'Between “{tokens[index]}” and “{tokens[index + 1]}”, the gap is {part_gap:.2f} s versus {ref_gap:.2f} s in the reference ({extra:.2f} s extra). ' + ("The reference joins these words closely." if misplaced else "The reference also pauses here, for less time."),
                    "Replay this boundary. Shorten the gap if you want the reference's flow; a longer rhetorical pause may be intentional.", "Between-word gap", ref_gap, part_gap, "s", gap=True)
                findings.append(finding)
                penalties["pauses"] += finding["severity_value"] / max(1, len(boundaries) / 6)
        # A weak word can invalidate its phrase without invalidating a clearly
        # quiet audio interval between independently reliable surrounding words.
        # Do not lower the word-quality gate or use the weak word's coordinates.
        for left, right, context in _uncertain_intervals(good, quality):
            ref_start, ref_end, ref_quiet = _longest_quiet(ref_audio, sample_rate, ref[left]["end"], ref[right]["start"], ref_baseline)
            part_start, part_end, part_quiet = _longest_quiet(part_audio, sample_rate, part[left]["end"], part[right]["start"], part_baseline)
            extra = part_quiet - ref_quiet
            if extra >= THRESHOLDS["pause_extra_seconds"] and part_quiet >= THRESHOLDS["pause_min_seconds"] and part_quiet / max(ref_quiet, THRESHOLDS["pause_reference_floor_seconds"]) >= THRESHOLDS["pause_ratio"]:
                finding = _finding("pauses", "Longer quiet gap between reliable words", [left, right], ref, part, float(np.mean(quality[context])), extra / 1.5,
                    f'Between reliably aligned “{tokens[left]}” and “{tokens[right]}”, the longest quiet interval is {part_quiet:.2f} s versus {ref_quiet:.2f} s in the reference ({extra:.2f} s extra). {right - left - 1} intervening word(s) have uncertain alignment; the gap is measured from audio at least {THRESHOLDS["pause_quiet_below_word_median_db"]:.0f} dB below reliable-word energy.',
                    "Listen to the quiet interval between these reliable words. Shorten it if you want the reference's flow; the uncertain words themselves are not scored.", "Longest quiet interval between reliable word anchors", ref_quiet, part_quiet, "s", gap=True)
                finding.update(start=round(part_start, 5), end=round(part_end, 5), reference_start=round(ref_start, 5), reference_end=round(ref_end, 5))
                findings.append(finding)
                penalties["pauses"] += finding["severity_value"] / max(1, len(boundaries) / 6)
    else:
        warnings.append("Scoring withheld: use at least two seconds of speech and five clearly aligned words, with reliable alignment across most of both readings.")
    dimensions = [{"key": key, "label": {"pacing": "Pacing", "pauses": "Pauses", "energy": "Relative energy"}[key], "score": round(100 * (1 - min(1, penalties[key])), 1) if reliable else None, "weight": normalized_weights[key]} for key in DEFAULT_WEIGHTS]
    score = round(sum(d["score"] * d["weight"] for d in dimensions), 1) if reliable else None
    findings.sort(key=lambda finding: (finding["start"], finding["type"]))
    caption = "Reference-comparison rubric score; differences can be intentional, and this is not a universal speaking-quality rating."
    if assessed < len(tokens):
        caption = f"Phrase scores cover {assessed} of {len(tokens)} words ({assessed / len(tokens):.0%}); unassessed phrases may contain differences. " + caption
    return {
        "summary": {"score": score, "flag_count": len(findings), "alignment_confidence": round(confidence, 4), "status": "complete" if reliable else "unreliable", "caption": caption if reliable else "Scores withheld because the available alignment or speech duration is insufficient.", "dimensions": dimensions, "assessed_word_count": assessed, "total_word_count": len(tokens), "assessed_fraction": round(assessed / len(tokens), 4)},
        "findings": findings,
        "rubric": {"version": RUBRIC_VERSION, "weights": normalized_weights, "thresholds": dict(THRESHOLDS)},
        "warnings": warnings,
    }
