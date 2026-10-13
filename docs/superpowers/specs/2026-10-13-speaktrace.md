# SpeakTrace approved concept

The user selected Track C and asked for an end-to-end hackathon prototype that runs on their laptop, entirely free, without a GPU. This specification records the concept presented in chat and the user's go-ahead to build it.

## Outcome

A local web workbench compares a reference speech and a participant reading of the same English transcript. It aligns actual audio to words, identifies rushed phrases, excessive pauses and local relative-energy drops, and explains each interval with measured evidence. Scores express a published reference-comparison rubric, not universal speaking quality or psychological diagnosis.

## Constraints

- CPU only; no paid APIs, accounts, cloud inference, or model training.
- Local FastAPI server and buildless HTML/CSS/JavaScript frontend. No frontend package installation or internet fonts needed.
- A pretrained English wav2vec2 CTC model supplies actual word alignment. Never substitute evenly spaced timestamps or injected labels for inference.
- Audio input: WAV, FLAC, OGG and MP3 if the decoder supports them; decoded mono at 16 kHz; 2 to 60 seconds; at most 20 MB per file.
- Supplied English transcript, maximum 150 words and 1600 characters. Numerals must be written as spoken words; unsupported text returns actionable validation errors.
- Three configurable score dimensions: pacing, pauses, energy; default weights 40/35/25, normalized to sum to one. Fixed versioned thresholds and deterministic explanations.
- Short, real, public-domain archive excerpts and generated single-factor variants are included. All generated examples are visibly labelled. Source provenance and transformation labels are separate from inference inputs.
- Evaluate held-out source groups, interval matching, clean controls and severity ordering. Do not invent independent human validation. Provide a human-recording protocol if volunteers are not available.
- Bundled examples work locally after setup. Cache model artifacts inside the project, excluded from source delivery. Inference does not send user recordings to any service.
- Explain uncertain alignments, refuse unsafe scoring when transcript mismatch/alignment quality is too poor, and keep warning/error/empty states usable.
- User recordings and reports live only in an ignored local runtime directory; retention and deletion behavior must be documented and deterministic.
- Prepare public-repository-ready source, dataset card, technical report, Devpost text and demo script. Do not claim an external repository, video upload, team registration or submission exists until actually completed.

## Product

One responsive studio-like screen: demo library, paired audio players, upload form, a shared transcript, analysis timeline, evidence inspector, dimension scores and report export. A methodology panel explains rubric, source licensing and limitations. Real computation or loading states replace fabricated initial scores.

## Validation

### Hardware amendment, 2026-10-13

The user subsequently reported an RTX 3050 with 4 GB VRAM. The installed GPU was identified as an RTX 3050 A Laptop GPU. Optional local CUDA inference was added and measured, while the CPU path remains supported. This supersedes the original CPU-only constraint; zero cost, no training and local processing still apply. See `reports/device-benchmark.json` for actual measurements and memory use.

Prove the CPU model on a real archive clip. Test alignment boundaries and repeated letters on handcrafted emissions; test silence/corrupt audio/incorrect transcript; test detector invariance to constant gain and leading silence, and detection on hand-labelled timing/energy fixtures. Test the real API and browser upload/demo/export flow. Run a fresh held-out benchmark and publish actual counts, metrics and limitations. A reviewer independent of implementation checks the integrated result.
