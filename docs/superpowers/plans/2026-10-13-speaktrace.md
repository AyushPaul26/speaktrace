# SpeakTrace Implementation Plan

> **For agentic workers:** Execute independent units against docs/API.md; use test-first development for the signal, alignment, validation and API behavior. One independent integrated review follows implementation.

**Goal:** Deliver a fully free local speech-comparison workbench with CPU and optional NVIDIA inference, plus an honest hackathon submission package.

**Architecture:** A local FastAPI service serves a buildless browser interface and queues bounded audio analyses. A pretrained wav2vec2 CTC model aligns words; deterministic signal features and reference-relative detectors compute evidence and scores. Archive audio, controlled augmentation, held-out evaluation and reports share a versioned manifest.

**Tech Stack:** Python 3.12, PyTorch 2.8 (CPU or CUDA 12.6), Transformers, NumPy, SciPy, librosa, SoundFile, FastAPI, Uvicorn, semantic HTML/CSS/JavaScript.

**Spec:** docs/superpowers/specs/2026-10-13-speaktrace.md

## Global constraints

CPU support plus optional GPU inference following the user's hardware correction, zero paid services; no fake timestamps/scores/validation. Raw audio stays local. 20 MB, 2–60 seconds, 150 words/1600 characters. Respect source provenance. Do not publish externally without the account details/authorization needed for that external step.

## Review focus

1. Transcript mismatch or low alignment confidence must withhold unreliable scores.
2. Audio corruption, silence, excessive duration and huge inputs must fail cleanly.
3. Constant recording gain and initial silence must not count as delivery flaws.
4. Pending jobs, server disconnection and rapid demo changes must not display stale results.
5. Dataset labels must not enter inference; grouping must prevent source-family leakage.

## Tasks

- [x] 1. Root: install isolated CPU dependencies, implement and test audio validation and actual CTC alignment (`speaktrace/audio.py`, `alignment.py`, `tests/test_alignment.py`, `test_audio.py`); verify on a real archive clip.
- [x] 2. Acoustic worker: implement `core/features.py`, `core/comparison.py`, hand-checked tests for pause/rate/energy/invariance/weights. Interfaces and JSON are in docs/API.md. Tests must fail before implementation and pass afterward.
- [x] 3. Data worker: source archive recordings with item-level rights, construct 4–6 excerpts and controlled variants with exact transformation labels, supply dataset card, generate reproducible manifest, and implement independent evaluation. Own `scripts/build_dataset.py`, `scripts/evaluate.py`, `data/`, relevant tests and dataset documentation.
- [x] 4. Frontend worker: implement responsive studio UI in `web/`, matching real API. Own DESIGN.md, premium-ui.json, design audit records. Cover upload validation, loading/error/empty, demo selection, paired playback, evidence navigation and exports.
- [x] 5. Root: FastAPI queue, upload limits, retention, media serving, reports, setup/launch scripts and end-to-end tests. `pytest -q` must pass; a real CPU demo and upload must complete.
- [x] 6. Root with independent reviewer: run held-out evaluation, inspect desktop/narrow UI and keyboard flow, fix actionable findings, prepare README, technical report, Devpost copy, demo script, source archive and final handoff. Report external publication/user-recording work honestly.

## Verification commands

`python -m pytest -q`; `node --check web/app.js`; `python scripts/evaluate.py`; `python scripts/verify_package.py`; browser interaction through the available computer-use tool; strict frontend-design audit. Use the local virtual environment for every Python command.
