# SpeakTrace Archive Perturbation Set v1

This is a small engineering benchmark of **real archival speech plus generated audio changes**. It tests whether a reference-comparison system detects controlled local edits. It does not establish which speakers are good speakers, whether a delivery choice is appropriate, or how the system performs on people recording themselves.

## Composition and provenance

Four English excerpts, each 20–30 seconds, come from two separate public-domain United States presidential recordings. Each has an unchanged control and nine single-factor variants: three edit types at three severities. This yields 4 reference files, 4 controls and 36 changed audio files. All deliverable files are mono 16 kHz PCM-16 WAV.

| ID | Speaker | Recording | Source offset | Duration | Split |
|---|---|---|---:|---:|---|
| jfk-welcome | John F. Kennedy | American University, 1963-06-10 | 39.045 s | 22.014 s | dev |
| jfk-learning | John F. Kennedy | American University, 1963-06-10 | 80.888 s | 27.549 s | dev |
| reagan-remembrance | Ronald Reagan | Challenger address, 1986-01-28 | 0.480 s | 23.950 s | test |
| reagan-families | Ronald Reagan | Challenger address, 1986-01-28 | 64.440 s | 22.012 s | test |

The [JFK Library sound item JFKWHA-190-002](https://www.jfklibrary.org/asset-viewer/archives/jfkwha-190-002) explicitly lists its copyright status as Public Domain. The source audio is the official downloadable MP3. Its [official transcript](https://www.jfklibrary.org/archives/other-resources/john-f-kennedy-speeches/american-university-19630610) supplies the excerpt text.

The [National Archives/DocsTeach Challenger item](https://docsteach.org/document/reagan-challenger/) identifies National Archives record 6014714 and explicitly states Public Domain, Free of Known Copyright Restrictions. The downloaded audio derivative is the [Commons OGG file](https://commons.wikimedia.org/wiki/File:Ronald_Reagan_speaks_on_the_Challenger_Space_Shuttle_Disaster.ogg), attributed to the Reagan Library's governmental channel and marked PD US Government. Text comes from the [Reagan Presidential Library transcript](https://www.reaganlibrary.gov/archives/speech/address-nation-explosion-space-shuttle-challenger).

Exact source URLs, item-level rights evidence, citations, download dates and SHA-256 checksums are in `data/sources.json`. Excerpt offsets and transcripts are in `data/excerpts.json`; the manifest records checksums of the delivered audio. The licensing claim concerns these specific United States federal government recordings. No blanket claim is made about all content hosted by these institutions or copyright law outside the United States. The project does not imply institutional or speaker endorsement.

## Excerpt and transcript preparation

Original recordings were decoded, converted to mono, and resampled using SciPy polyphase resampling. Candidate source windows were recognized with the project's actual pretrained wav2vec2 model. Their text was compared against the official transcripts; constrained CTC alignment then located word boundaries. Selected excerpts use contiguous source audio and official transcript slices, with numerals written as spoken words. The JFK excerpt uses "nineteen fourteen" for the printed date.

The final quantized WAV files are aligned again. `data/references/*.json` records the independent recognized text, average alignment confidence, reliable-word coverage and greedy-transcript agreement. These are automatic consistency checks, not proof from a human listening audit. No human-verified word timestamp annotations are claimed. Boundaries have approximately 20 ms model resolution; crop margins stay inside neighboring word gaps.

## Controlled edits

The edit location is fixed at one third of the transcript before evaluation. Energy affects six consecutive words; rate affects ten. Pause insertion occurs halfway between the first selected word and its successor. This choice is independent of the detector's phrase boundaries. Some changes can span two detector windows and may therefore be missed or localized loosely.

| Type | Mild | Moderate | Severe | Operation |
|---|---:|---:|---:|---|
| Local energy drop | −5 dB | −9 dB | −14 dB | Multiply the selected interval by a linear amplitude gain; 10 ms transition ramps |
| Extra pause | +0.65 s | +1.10 s | +1.80 s | Insert digital silence within an existing inter-word gap |
| Local rushed phrase | 1.35× | 1.65× | 2.00× | librosa phase-vocoder time stretch on the selected interval, preserving pitch approximately |
| Clean control | unchanged | — | — | Write the same decoded reference samples as PCM-16 |

Parameters were set before inspecting held-out evaluation results. There is no random noise or random placement, and no learned augmentation model. The JSON `transform` field records the exact word indices, input span, parameter and operation. The `labels` field records the actual waveform operation span **in participant time**. For pauses the label is the entire altered gap, including the original gap; for pacing it ends at the compressed interval's end. Rate changes shift all following audio. Gain changes do not change timing.

Generated examples are labelled as generated in the interface and manifest. These are signal-processing edits of a real voice, not new speech synthesis or actual mistakes by the historical speaker. Phase-vocoder artifacts and digital-silence boundaries may be easier to detect than natural delivery changes. The clean controls share the same PCM serialization path, but do not simulate a different recording environment.

**Observed pacing confound:** the development-only check in `reports/development-pacing-dsp-check.json` confirmed exact 1.35× sample compression and bit-identical audio outside both edited regions. However, those regions also lost 3.21–3.54 dB RMS and their greedy-transcript agreement fell from 0.80 to 0.10. Pitch tracking was unstable in one edited region. The phase-vocoder examples therefore contain substantial artifacts and are not validated as isolated natural rushing. These failures are retained rather than hiding the examples or loosening alignment confidence. A future separately versioned dataset should validate a speech-oriented time-stretch method with independent listening and held-out recordings.

## Split and independence

The entire Kennedy recording and all descendants form the development group. The entire Reagan recording and all descendants form the held-out test group. No speaker, source recording, original excerpt or transformed descendant crosses groups. The evaluator rejects a source-group split conflict.

The detector receives only the reference audio, participant audio, transcript and independently inferred word timings. Generator annotations, expected flaw, severity, edit parameters and event labels do not enter inference. Generator word timings are stored under `data/annotations` solely for reproducibility; the application must not consume these files. All comparisons run the real alignment and scoring policy used by the application. The held-out set contains a single source group and is too small for population estimates or confident statistical intervals.

## Reproduction and evaluation

From the project root, after setup and model installation:

```powershell
./.venv/Scripts/python.exe scripts/build_dataset.py
./.venv/Scripts/python.exe scripts/evaluate.py
```

The builder verifies downloaded source checksums before processing. `--skip-download` requires local sources. Raw source recordings are large and excluded from the source delivery; the source URLs and checksums permit rebuilding. The short references, variants, and genuine generator CTC annotations are bundled. To reconstruct only the variants **offline, without raw sources or model inference**, run `./.venv/Scripts/python.exe scripts/build_dataset.py --variants-only`. This uses the bundled reference WAVs, manifest and `data/annotations/*.json` word boundaries. These annotations remain generator inputs only.

The evaluator computes fresh local alignments by default, including controls. It applies the application's transcript-mismatch policy. Set `$env:SPEAKTRACE_DEVICE='cpu'` before the evaluation command to force a reproducible CPU run; optional GPU execution records actual device metadata for each alignment, including any CPU fallback. `--use-cache` explicitly enables a separate alignment cache keyed by audio SHA-256, transcript, model identity/revision, alignment implementation hash and compute device/software; cache hits are counted in the report. Every comparison is recomputed even with cached alignments.

`reports/evaluation.json` is the canonical machine-readable result. Events are matched one-to-one by type with interval IoU at least 0.30, maximizing match count and then total overlap. Wrong-type events, duplicates and unmatched events are false positives. Misses, including withheld or failed analyses, are false negatives. It reports event precision/recall/F1, mean IoU and mean absolute start/end boundary error on matched events, clean-control false-positive rate, withheld/error count and score ordering across severities. Unmatched events are not hidden in the boundary-error statistic. Severity-ordering counts distinguish nonincreasing scores from strictly decreasing scores, so ties do not masquerade as discrimination.

The initial rubric 1.0.0 run is preserved as `reports/evaluation-v1.0.0-baseline.json`: 44 fresh alignments, zero cache hits, 108.209 seconds. Its test group had 4 true-positive events, 1 false-positive event and 14 misses; both test controls had zero flags. Subsequent engineering fixes investigated development-group evidence. Reusing the same test group after seeing its original aggregate results is a development rerun, not a new untouched external validation set. Source-disjoint grouping remains intact. The excerpts, edit placement and severity parameters remain unchanged.

The final rubric 1.1.0 fresh CPU result is preserved in `reports/evaluation-v1.1.0-fresh-cpu.json` (44 fresh alignments, zero hits, 133.432 seconds). The canonical `reports/evaluation.json` was then rerun against final pipeline source with `--use-cache`: 44 explicit cache hits, zero fresh alignments, all comparisons recomputed, 10.240 seconds. Metrics are identical; test-group counts are 7 TP, 1 FP and 11 FN. `reports/EVALUATION.md` reports the breakdown, including missed pacing examples and limited energy sensitivity.

## Limitations and human validation protocol

No volunteers or independent human raters contributed to this dataset. No real-participant accuracy, clinical utility, fairness or public-speaking improvement claim is supported. The set contains two adult male American-English presidential speakers, prepared public addresses, and old broadcast audio. It does not cover other accents, women, children, spontaneous speech, noisy laptop microphones, speech differences, stuttering, accessibility needs or recordings by a different speaker reading the same words. The solemn content of the Challenger address illustrates why an unusual pause may be expressive rather than erroneous.

Before using this as participant-performance evidence, recruit consenting adult volunteers across voice/accent and recording conditions; obtain permission for the specific retention and sharing plan. Each should record a neutral 20–30 second transcript normally, then repeat it with one instructed local change and natural uncontrolled variation. Use source/speaker-disjoint splits. At least two independent raters, blinded to system output and synthetic labels, should mark perceived rushing, excessive pauses and local audibility drops with start/end times and uncertainty. Report inter-rater agreement, adjudication rules, all failed/withheld cases, per-group errors, boundary tolerance and clean recordings. Freeze thresholds before opening the held-out group. Report synthetic and human-recording results separately.
