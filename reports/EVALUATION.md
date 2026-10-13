# Archive benchmark results

The canonical result is `evaluation.json`, produced with rubric `reference-relative-1.1.0` and the unchanged dataset v1.0.0. This is a source-disjoint **development rerun** after the initial test-group aggregate results were observed. It is not independent human validation or a new untouched test set.

The canonical run reused 44 explicitly enabled alignment cache entries, made zero fresh alignment calls, recomputed every comparison and took 10.240 seconds. Its pipeline and comparison source hashes match the final source. Per-example cache flags and actual device metadata are recorded. The underlying fresh run is preserved as `evaluation-v1.1.0-fresh-cpu.json`: 44 fresh alignments, zero cache hits, 133.432 seconds. Both used CPU with PyTorch 2.8.0+cpu, float32, and wav2vec2-base-960h revision `22aad52d435eb6dbaf354bdad9b0da84ce7d6156`; their reported metrics are identical. All examples completed; no full-recording scores were withheld. Some individual regions were skipped because of weak alignment. No GPU speed claim comes from these runs.

| Split | Examples | TP / FP / FN | Precision | Recall | F1 | Matched mean IoU | Matched boundary MAE |
|---|---:|---|---:|---:|---:|---:|---:|
| Development: Kennedy source | 20 | 8 / 1 / 10 | 0.889 | 0.444 | 0.593 | 0.861 | 0.138 s |
| Test group reused: Reagan source | 20 | 7 / 1 / 11 | 0.875 | 0.389 | 0.538 | 0.918 | 0.065 s |

Events use one-to-one same-type matching at IoU ≥ 0.30. Boundary error and overlap are conditional on matched events; misses remain in recall. Both clean controls in each split produced zero flags (0/4 combined), a very small control sample.

| Type | Development detections | Test-group detections | Test-group false positives |
|---|---:|---:|---:|
| Added pauses | 6 / 6 | 6 / 6 | 0 |
| Local energy reductions | 2 / 6 | 1 / 6 | 1 |
| Generated pacing changes | 0 / 6 | 0 / 6 | 0 |

For severity order, 6/6 development triples and 5/6 test-group triples had nonincreasing scores. Only 3/6 and 2/6 respectively were strictly decreasing. Constant perfect scores on missed examples contribute ties and do not show severity discrimination.

The original rubric 1.0.0 report is preserved in `evaluation-v1.0.0-baseline.json`. Its test-group counts were 4 TP, 1 FP, 14 FN. The subsequent pause fix used development evidence and independently measured quiet runs between reliable word anchors; the original waveforms, edit labels and transformation parameters were unchanged.

The pacing failures have a demonstrated generator confound. `development-pacing-dsp-check.json` found accurate sample compression and unchanged audio outside the edits, but the phase-vocoder regions lost about 3.2–3.5 dB RMS and their greedy transcript agreement fell from 0.80 to 0.10. Weak word alignments correctly prevent trusted pacing scoring in those regions. These examples do not validate natural-rushing detection. Energy sensitivity is also limited. The overall numbers should not be presented as strong coaching accuracy.

`dataset-reproduction.json` verifies that offline regeneration from bundled reference WAVs and genuine generator annotations reproduces all 40 variant files and the manifest byte-for-byte, without network access or model inference. `docs/DATASET_CARD.md` documents provenance, split construction, methods, limitations and a proposed human-recording validation protocol. No independent human study was performed.
