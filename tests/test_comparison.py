"""Hand-specified word durations/gaps test observable comparison behavior."""
import copy
import importlib
import json

import numpy as np
import pytest


SR = 16000
TEXT = "we can speak with steady rhythm then take time to explain the idea and make each point clear"
TOKENS = TEXT.split()


def recording(durations=None, gaps=None, levels=None, offset=.2):
    durations = durations if durations is not None else [.25] * 18
    gaps = gaps if gaps is not None else [.08] * 17
    levels = levels if levels is not None else [.2] * 18
    cursor = offset
    words = []
    for index, token in enumerate(TOKENS):
        words.append({"word": token, "start": cursor, "end": cursor + durations[index], "score": .95})
        cursor += durations[index] + (gaps[index] if index < 17 else 0)
    audio = np.zeros(round((cursor + .2) * SR))
    for word, level in zip(words, levels):
        start, end = round(word["start"] * SR), round(word["end"] * SR)
        t = np.arange(end - start) / SR
        audio[start:end] = level * np.sin(2 * np.pi * 200 * t)
    return audio, words


def compare(reference=None, participant=None, transcript=TEXT, weights=None):
    ref_audio, ref_words = reference if reference is not None else recording()
    part_audio, part_words = participant if participant is not None else recording()
    function = importlib.import_module("speaktrace.core.comparison").compare_recordings
    return function(ref_audio, part_audio, SR, ref_words, part_words, transcript, weights)


def of_type(result, kind):
    return [finding for finding in result["findings"] if finding["type"] == kind]


def test_clean_recording_has_no_findings_and_full_rubric_score():
    result = compare()
    json.dumps(result, allow_nan=False)
    assert result["findings"] == []
    assert result["summary"]["score"] == 100
    assert result["summary"]["status"] == "complete"
    assert result["summary"]["flag_count"] == 0
    assert sum(result["rubric"]["weights"].values()) == pytest.approx(1)
    assert result["rubric"]["version"]


def test_local_rush_uses_actual_word_articulation_and_coordinates():
    audio, words = recording(durations=[.25] * 6 + [.125] * 6 + [.25] * 6)
    result = compare(participant=(audio, words))
    flags = of_type(result, "pacing")
    assert len(flags) == 1
    finding = flags[0]
    assert finding["word_indices"] == [6, 7, 8, 9, 10, 11]
    assert finding["start"] == pytest.approx(words[6]["start"])
    assert finding["end"] == pytest.approx(words[11]["end"])
    assert finding["evidence"]["reference"] == pytest.approx(240)
    assert finding["evidence"]["participant"] == pytest.approx(480)
    assert not of_type(result, "pauses")
    assert not of_type(result, "energy")


def test_extra_pause_is_located_between_words_without_pacing_penalty():
    audio, words = recording(gaps=[.08] * 8 + [1.08] + [.08] * 8)
    result = compare(participant=(audio, words))
    flags = of_type(result, "pauses")
    assert len(flags) == 1
    assert flags[0]["start"] == pytest.approx(words[8]["end"])
    assert flags[0]["end"] == pytest.approx(words[9]["start"])
    assert flags[0]["evidence"]["reference"] == pytest.approx(.08)
    assert flags[0]["evidence"]["participant"] == pytest.approx(1.08)
    assert not of_type(result, "pacing")
    assert not of_type(result, "energy")


def test_local_energy_drop_is_measured_relative_to_each_recording():
    result = compare(participant=recording(levels=[.2] * 6 + [.04] * 6 + [.2] * 6))
    flags = of_type(result, "energy")
    assert len(flags) == 1
    assert flags[0]["word_indices"] == [6, 7, 8, 9, 10, 11]
    assert flags[0]["evidence"]["reference"] == pytest.approx(0, abs=.01)
    assert flags[0]["evidence"]["participant"] == pytest.approx(-13.9794, abs=.01)
    assert not of_type(result, "pacing")
    assert not of_type(result, "pauses")


def test_constant_gain_does_not_change_flags_or_score():
    audio, words = recording(levels=[.2] * 6 + [.04] * 6 + [.2] * 6)
    original = compare(participant=(audio, words))
    quieter = compare(participant=(audio * .035, words))
    assert quieter["summary"]["score"] == original["summary"]["score"]
    assert quieter["findings"] == original["findings"]
    clean_audio, clean_words = recording()
    assert compare(participant=(clean_audio * .035, clean_words))["findings"] == []


def test_leading_silence_changes_only_elapsed_coordinates():
    audio, words = recording(durations=[.25] * 6 + [.125] * 6 + [.25] * 6)
    original = compare(participant=(audio, words))
    shifted_words = [{**word, "start": word["start"] + 1.7, "end": word["end"] + 1.7} for word in words]
    shifted_audio = np.concatenate([np.zeros(round(1.7 * SR)), audio])
    shifted = compare(participant=(shifted_audio, shifted_words))
    assert shifted["summary"]["score"] == original["summary"]["score"]
    assert len(shifted["findings"]) == len(original["findings"])
    for before, after in zip(original["findings"], shifted["findings"]):
        assert after["start"] == pytest.approx(before["start"] + 1.7)
        assert after["evidence"] == before["evidence"]
        assert after["severity_value"] == before["severity_value"]


def test_low_confidence_recording_withholds_scores_and_findings():
    audio, words = recording(durations=[.125] * 18)
    for word in words:
        word["score"] = .1
    result = compare(participant=(audio, words))
    assert result["summary"]["score"] is None
    assert result["summary"]["status"] == "unreliable"
    assert all(d["score"] is None for d in result["summary"]["dimensions"])
    assert result["findings"] == []
    assert result["warnings"]


def test_local_low_confidence_region_is_skipped_but_good_region_is_compared():
    audio, words = recording(durations=[.125] * 12 + [.25] * 6)
    words[8]["score"] = .05
    result = compare(participant=(audio, words))
    flags = of_type(result, "pacing")
    assert result["summary"]["status"] == "complete"
    assert len(flags) == 1
    assert flags[0]["word_indices"] == list(range(6))
    assert result["warnings"]


@pytest.mark.parametrize("mutate", [
    lambda words: [],
    lambda words: words[:-1],
    lambda words: [{**words[0], "word": "different"}] + words[1:],
    lambda words: [{**words[0], "start": float("nan")}] + words[1:],
    lambda words: [{**words[0], "end": 1000}] + words[1:],
    lambda words: [{**words[0], "score": float("inf")}] + words[1:],
    lambda words: [{**words[0], "score": -1}] + words[1:],
    lambda words: [{**words[0], "end": words[0]["start"]}] + words[1:],
    lambda words: [None] + words[1:],
    lambda words: [words[1], words[0]] + words[2:],
])
def test_malformed_or_wrong_word_alignment_fails_cleanly(mutate):
    audio, words = recording()
    with pytest.raises(ValueError):
        compare(participant=(audio, mutate(copy.deepcopy(words))))


@pytest.mark.parametrize("weights", [{"pacing": -1}, {"pacing": float("nan")}, {"pacing": float("inf")}, {"pacing": 0, "pauses": 0, "energy": 0}, {"pacing": "40"}, {"unrecognized": 1}, {"pacing": True}])
def test_invalid_weights_are_rejected(weights):
    with pytest.raises(ValueError):
        compare(weights=weights)


def test_custom_weights_apply_to_actual_dimension_scores():
    participant = recording(durations=[.25] * 6 + [.125] * 6 + [.25] * 6)
    result = compare(participant=participant, weights={"pacing": 1, "pauses": 0, "energy": 0})
    dimension = next(d for d in result["summary"]["dimensions"] if d["key"] == "pacing")
    assert result["summary"]["score"] == dimension["score"] < 100


def test_short_clip_withholds_scoring():
    audio, words = recording(durations=[.04] * 18, gaps=[.005] * 17, offset=0)
    result = compare(reference=(audio, words), participant=(audio, words))
    assert result["summary"]["score"] is None
    assert result["warnings"]


def test_silent_audio_is_rejected_even_with_plausible_words():
    audio, words = recording()
    with pytest.raises(ValueError):
        compare(participant=(np.zeros_like(audio), words))


def test_more_severe_rush_receives_lower_score():
    mild = compare(participant=recording(durations=[.25] * 6 + [.18] * 6 + [.25] * 6))
    severe = compare(participant=recording(durations=[.25] * 6 + [.1] * 6 + [.25] * 6))
    assert severe["summary"]["score"] < mild["summary"]["score"] < 100


def test_leading_padding_cannot_make_an_insufficient_clip_scoreable():
    audio, words = recording(durations=[.04] * 18, gaps=[.005] * 17, offset=0)
    padded = np.concatenate([np.zeros(3 * SR), audio])
    shifted = [{**word, "start": word["start"] + 3, "end": word["end"] + 3} for word in words]
    result = compare(reference=(padded, shifted), participant=(padded, shifted))
    assert result["summary"]["score"] is None


def test_dc_offset_is_not_speech_for_scoring():
    audio, words = recording()
    with pytest.raises(ValueError):
        compare(participant=(np.full_like(audio, .2), words))


def test_unaligned_audio_outside_words_cannot_rescue_silent_word_intervals():
    audio, words = recording(offset=2.2)
    silent_words = np.zeros_like(audio)
    silent_words[:2 * SR] = .2 * np.sin(2 * np.pi * 200 * np.arange(2 * SR) / SR)
    result = compare(participant=(silent_words, words))
    assert result["summary"]["score"] is None
    assert result["findings"] == []


def test_large_finite_weights_normalize_without_overflow():
    result = compare(weights={"pacing": 1e308, "pauses": 1e308, "energy": 1e308})
    assert result["summary"]["score"] == 100
    assert sum(result["rubric"]["weights"].values()) == pytest.approx(1)
    json.dumps(result, allow_nan=False)


def test_more_severe_pause_receives_lower_pause_score():
    mild = compare(participant=recording(gaps=[.08] * 8 + [.48] + [.08] * 8))
    severe = compare(participant=recording(gaps=[.08] * 8 + [1.38] + [.08] * 8))
    assert severe["summary"]["score"] < mild["summary"]["score"] < 100


def test_more_severe_energy_drop_receives_lower_energy_score():
    mild = compare(participant=recording(levels=[.2] * 6 + [.09] * 6 + [.2] * 6))
    severe = compare(participant=recording(levels=[.2] * 6 + [.025] * 6 + [.2] * 6))
    assert severe["summary"]["score"] < mild["summary"]["score"] < 100


@pytest.mark.parametrize("written_first,aligned_first", [("we\u2018re", "we're"), ("we\u2019re", "we're"), ("we're", "we're"), ("\uff37\uff45", "we")])
def test_supported_transcript_typography_matches_canonical_alignment(written_first, aligned_first):
    audio, words = recording()
    words[0]["word"] = aligned_first
    transcript = written_first + TEXT[2:]
    result = compare(reference=(audio, words), participant=(audio, words), transcript=transcript)
    assert result["summary"]["score"] == 100
    assert result["findings"] == []


def test_quiet_pause_is_corroborated_between_reliable_anchors_when_one_word_is_uncertain():
    audio, words = recording(gaps=[.08] * 8 + [1.08] + [.08] * 8)
    words[8]["score"] = .1
    result = compare(participant=(audio, words))
    flags = of_type(result, "pauses")
    assert len(flags) == 1
    assert flags[0]["word_indices"] == [7, 9]
    assert flags[0]["start"] == pytest.approx(words[8]["end"], abs=.021)
    assert flags[0]["end"] == pytest.approx(words[9]["start"], abs=.021)
    assert flags[0]["evidence"]["participant"] == pytest.approx(1.08, abs=.021)
    assert flags[0]["evidence"]["reference"] == pytest.approx(.08, abs=.021)
    assert flags[0]["confidence"] >= .55
    assert "quiet" in flags[0]["explanation"].lower()
    assert "uncertain" in flags[0]["explanation"].lower()
    assert not of_type(result, "pacing")


def test_uncertain_word_plus_a_noisy_gap_does_not_claim_a_quiet_pause():
    audio, words = recording(gaps=[.08] * 8 + [1.08] + [.08] * 8)
    words[8]["score"] = .1
    a, b = round(words[8]["end"] * SR), round(words[9]["start"] * SR)
    audio[a:b] = np.random.default_rng(42).normal(0, .08, b - a)
    assert of_type(compare(participant=(audio, words)), "pauses") == []


def test_uncertain_alignment_does_not_flag_a_pause_already_in_reference():
    audio, words = recording(gaps=[.08] * 8 + [1.08] + [.08] * 8)
    participant_words = copy.deepcopy(words)
    participant_words[8]["score"] = .1
    assert of_type(compare(reference=(audio, words), participant=(audio, participant_words)), "pauses") == []


def test_pause_fallback_requires_reliable_context_on_both_sides():
    audio, words = recording(gaps=[.08] * 8 + [1.08] + [.08] * 8)
    for index in range(6, 10):
        words[index]["score"] = .1
    assert of_type(compare(participant=(audio, words)), "pauses") == []


def test_partial_comparison_explicitly_reports_unassessed_phrase_coverage():
    audio, words = recording()
    words[8]["score"] = .1
    result = compare(participant=(audio, words))
    assert result["summary"]["assessed_word_count"] == 12
    assert result["summary"]["total_word_count"] == 18
    assert result["summary"]["assessed_fraction"] == pytest.approx(2 / 3, abs=.001)
    assert "12 of 18" in result["summary"]["caption"]
    assert any("unassessed" in warning.lower() for warning in result["warnings"])
