"""Handcrafted CTC emissions catch timing and repeated-token alignment bugs."""
import numpy as np
import pytest

from speaktrace.alignment import ctc_align, normalize_transcript, transcript_similarity


def emissions(sequence, vocabulary_size=5):
    result = np.full((len(sequence), vocabulary_size), -12.0, dtype=np.float32)
    result[np.arange(len(sequence)), sequence] = -0.001
    return result


def test_ctc_alignment_recovers_actual_frame_boundaries():
    spans = ctc_align(emissions([0, 1, 1, 0, 2, 2, 0, 3, 0]), [1, 2, 3], blank_id=0)
    assert [(s["start"], s["end"]) for s in spans] == [(1, 3), (4, 6), (7, 8)]
    assert all(s["score"] > 0.99 for s in spans)


def test_repeated_letters_require_separate_blank_frames():
    spans = ctc_align(emissions([0, 1, 0, 1, 0, 2, 0]), [1, 1, 2], blank_id=0)
    assert [(s["start"], s["end"]) for s in spans] == [(1, 2), (3, 4), (5, 6)]


def test_impossible_ctc_sequence_fails_instead_of_inventing_times():
    with pytest.raises(ValueError, match="align"):
        ctc_align(emissions([1, 1]), [1, 1], blank_id=0)


def test_normalization_keeps_apostrophes_but_rejects_numbers_and_empty_text():
    assert normalize_transcript("We’re ready — let's begin!") == ["WE'RE", "READY", "LET'S", "BEGIN"]
    for invalid in ["", "   ", "There are 42 people", "你好"]:
        with pytest.raises(ValueError):
            normalize_transcript(invalid)


def test_unrelated_transcript_does_not_pass_agreement_check():
    assert transcript_similarity("we choose to go to the moon", "we choose to go to the moon") == 1.0
    assert transcript_similarity("we choose to go to the moon", "tomorrow the garden is closed") < 0.3


def test_alignment_rejects_nonfinite_emissions():
    bad = emissions([0, 1, 2])
    bad[0, 0] = np.nan
    with pytest.raises(ValueError):
        ctc_align(bad, [1, 2], blank_id=0)
