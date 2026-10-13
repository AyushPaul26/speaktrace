# SpeakTrace

## Project name
SpeakTrace: speech feedback you can hear and inspect

## Elevator pitch
A speech studio that compares two readings of the same words, highlights measured differences in pacing, pauses and relative energy, and lets you hear the evidence behind each finding.

## Track
Track C - Explainable contrastive speech analytics.

## Inspiration
An overall speaking score rarely explains what someone should practice. We wanted to connect each piece of feedback to the words, the two recordings, the measured difference and a transparent scoring rule. We also wanted a useful prototype without paid APIs or model training.

## What it does
Provide a reference, a second reading and their shared English transcript. SpeakTrace computes actual word alignment, acoustic diagnostics and a reference-relative rubric. Select a word or finding to seek each recording to its own corresponding time. Inspect the waveform and measurements, change rubric weights, and export the analysis as JSON or a printable report. Archive examples show controlled audio edits with separate evaluation labels.

## How we built it
A local FastAPI server serves a buildless JavaScript interface. A pinned pretrained wav2vec2 model supplies acoustic emissions; an explicit CTC Viterbi decoder aligns the supplied transcript. NumPy/SciPy features support deterministic pace, pause and relative-energy comparisons. Low alignment quality and transcript disagreement constrain or withhold assessment. Inference runs locally, with CPU support and optional NVIDIA acceleration; nothing needs to be trained.

The Vercel version uses the same pipeline on CPU with a 30-second limit per recording. The browser prepares mono WAV audio before upload and keeps playback and reports in the current tab. Hosted audio is sent to the cloud; local mode keeps recordings on the user's machine and supports up to 60 seconds. No paid model API is used.

The included benchmark contains four real public-domain excerpts from two source recordings, four unchanged controls and 36 generated edits. Each edit has its actual waveform-operation span. Source families remain separated between development and test groups. The evaluator performs type-aware one-to-one temporal matching and includes missed, failed and withheld cases.

## Challenges and what we learned
Constrained alignment can fit words to unclear audio, so an aligned path alone is insufficient evidence. Independent transcript agreement and local reliability checks are essential. We also found that a phase-vocoder speed edit can damage intelligibility: a nominal pacing intervention can introduce other acoustic changes. The preserved baseline, diagnostics and final development rerun document this limitation rather than disguising it as human validation.

## Results
The final development rerun on the 20-example source-disjoint test group produced 7 true positives, 1 false positive and 11 misses (precision 0.875, recall 0.389, F1 0.538). All six pause edits were detected; energy detection found one of six edits and pacing detection found none. The pacing generator's recognition artifacts limit interpretation. These results establish a working evidence pipeline and expose its current limits; they do not establish natural-speech assessment accuracy or untouched validation.

On an RTX 3050 A Laptop GPU with 4 GB VRAM, three warm, uncached alignments of one 22.012-second clip had a median runtime of 0.184 seconds versus 1.792 seconds on CPU (9.73x for alignment). A separate 60-second tiled-audio inference stress test peaked at 1122.7 MiB allocated GPU memory. These are hardware measurements on specific inputs, not whole-app speed claims. Verification passed 124 Python tests and 20 JavaScript tests. The local browser workflow passed 13 checks, with hosted browser conversion and transport checked separately. The report, machine-readable evaluation and verification records are included.

## What is next
Evaluate real consenting participants with independent raters; broaden voices, accents and microphone conditions; improve confidence calibration and natural rushed-speech detection. Keep detected reference differences separate from a universal judgment of speaking ability.

## Built With
Python, PyTorch, Hugging Face Transformers, wav2vec2, NumPy, SciPy, librosa, SoundFile, FastAPI, Uvicorn, HTML, CSS, JavaScript, GitHub, Vercel, OpenAI Codex, ChatGPT.

## AI assistance disclosure
OpenAI Codex/ChatGPT assisted with research, architecture, implementation, tests, design and documentation. The entrant must review the work, understand the method and include this disclosure in the public README and Built With fields. No human participant study is claimed.

## Account fields to complete
Try it out: https://speaktrace-amber.vercel.app . Public source repository: https://github.com/AyushPaul26/speaktrace . The entrant still needs to supply actual team members and Devpost accounts, and the recorded YouTube demo URL. Upload the PDF technical report and link the included dataset. Check the organizer's current submission form and deadline before submitting.
