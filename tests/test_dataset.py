"""Tests for label coordinate integrity and independent evaluation matching."""
import unittest
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import numpy as np


class DatasetTests(unittest.TestCase):
    def setUp(self):
        self.audio = np.ones(4000, dtype=np.float32) * 0.2
        self.words = [
            {"word": "ONE", "start": 0.2, "end": 0.6},
            {"word": "TWO", "start": 0.8, "end": 1.2},
            {"word": "THREE", "start": 1.4, "end": 1.8},
            {"word": "FOUR", "start": 2.2, "end": 2.8},
        ]

    def test_energy_only_changes_labelled_samples(self):
        # Catches accidental global normalization or the wrong time interval.
        from scripts.build_dataset import augment_audio
        result, labels, transform = augment_audio(self.audio, 1000, self.words, "energy", 6, (1, 2))
        np.testing.assert_array_equal(result[:800], self.audio[:800])
        np.testing.assert_array_equal(result[1800:], self.audio[1800:])
        self.assertAlmostEqual(float(result[1000]), 0.10023745, places=6)
        self.assertEqual(labels, [{"type": "energy", "start": 0.8, "end": 1.8}])
        self.assertEqual(transform["reduction_db"], 6)

    def test_pause_label_is_on_variant_time_and_duration_is_exact(self):
        # Catches labelling only inserted silence rather than the full changed gap.
        from scripts.build_dataset import augment_audio
        result, labels, transform = augment_audio(self.audio, 1000, self.words, "pauses", 0.75, (1, 2))
        self.assertEqual(len(result), 4750)
        self.assertEqual(labels, [{"type": "pauses", "start": 1.2, "end": 2.15}])
        self.assertEqual(transform["insertion_seconds"], 1.3)
        np.testing.assert_array_equal(result[1300:2050], np.zeros(750))
        np.testing.assert_array_equal(result[2050:], self.audio[1300:])

    def test_clean_control_is_an_independent_unchanged_copy(self):
        from scripts.build_dataset import augment_audio
        result, labels, _ = augment_audio(self.audio, 1000, self.words, "clean", 0, (1, 2))
        self.assertEqual(labels, [])
        np.testing.assert_array_equal(result, self.audio)
        self.assertIsNot(result, self.audio)

    def test_pacing_preserves_pitch_and_updates_duration(self):
        # Catches resampling-based speedups which would change the voice pitch.
        from scripts.build_dataset import augment_audio
        sr = 16000
        audio = (0.2 * np.sin(2 * np.pi * 220 * np.arange(sr * 4) / sr)).astype(np.float32)
        result, labels, _ = augment_audio(audio, sr, self.words, "pacing", 2, (1, 2))
        self.assertEqual(len(result), 56000)
        self.assertEqual(labels, [{"type": "pacing", "start": 0.8, "end": 1.3}])
        segment = result[14000:19000]
        peak = np.fft.rfftfreq(len(segment), 1 / sr)[np.argmax(abs(np.fft.rfft(segment)))]
        self.assertAlmostEqual(peak, 220, delta=5)

    def test_matching_is_one_to_one_and_type_aware(self):
        # Catches duplicate detections inflated into multiple true positives.
        from scripts.evaluate import match_events
        gold = [{"type": "energy", "start": 1, "end": 3}]
        found = [{"type": "energy", "start": 1, "end": 3},
                 {"type": "energy", "start": 1.1, "end": 3.1},
                 {"type": "pauses", "start": 1, "end": 3}]
        result = match_events(gold, found, 0.3)
        self.assertEqual((result["tp"], result["fp"], result["fn"]), (1, 2, 0))
        self.assertEqual(result["matched_ious"], [1.0])
        self.assertEqual(result["boundary_errors_seconds"], [0.0])

    def test_source_group_leakage_rejected(self):
        from scripts.evaluate import validate_source_splits
        refs = [{"source_group": "same", "split": "dev"}, {"source_group": "same", "split": "test"}]
        with self.assertRaisesRegex(ValueError, "source"):
            validate_source_splits(refs)

    def test_iou_of_nonoverlapping_events_is_zero(self):
        from scripts.evaluate import interval_iou
        self.assertEqual(interval_iou({"start": 1, "end": 2}, {"start": 3, "end": 4}), 0)

    def test_per_type_clean_false_positive_rate_uses_that_type(self):
        # Catches counting an energy false alarm as a pause false alarm.
        from scripts.evaluate import aggregate
        rows = [{"flaw": "clean", "labels": [], "status": "complete",
                 "findings": [{"type": "energy", "start": 1, "end": 2}]}]
        self.assertEqual(aggregate(rows, "pauses")["clean_controls_with_flags"], 0)
        self.assertEqual(aggregate(rows, "energy")["clean_controls_with_flags"], 1)

    def test_offline_regeneration_uses_bundled_audio_and_annotations(self):
        # Catches accidental dependence on source downloads or model inference.
        import soundfile as sf
        from scripts.build_dataset import regenerate_variants
        with TemporaryDirectory(dir=Path(__file__).resolve().parents[1] / ".runtime") as temp:
            root = Path(temp)
            (root / "data/references").mkdir(parents=True)
            (root / "data/annotations").mkdir()
            sf.write(root / "data/references/fixture.wav", np.repeat(self.audio, 16), 16000)
            reference = {"id": "fixture", "audio": "data/references/fixture.wav", "variants": []}
            manifest = {"version": "1.0.0", "references": [reference]}
            (root / "data/manifest.json").write_text(json.dumps(manifest))
            (root / "data/annotations/fixture.json").write_text(json.dumps({"words": self.words}))
            rebuilt = regenerate_variants(root)
            variants = rebuilt["references"][0]["variants"]
            self.assertEqual(len(variants), 10)
            self.assertTrue(all((root / variant["audio"]).is_file() for variant in variants))
            clean = root / next(variant["audio"] for variant in variants if variant["flaw"] == "clean")
            self.assertEqual(clean.read_bytes(), (root / reference["audio"]).read_bytes())


if __name__ == "__main__":
    unittest.main()
