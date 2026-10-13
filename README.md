# SpeakTrace

**Hear it. See it. Refine it.** A free, local speech comparison studio for Track C of the Multimodal AI Hackathon 2026. It supports CPU inference and optional NVIDIA acceleration.

[Public source repository](https://github.com/AyushPaul26/speaktrace)

Compare a reference recording and a participant reading of the same English transcript. SpeakTrace aligns actual speech to words, measures local pacing, pause and energy differences, and links every detected interval to audible evidence and a reproducible rubric.

## Run on Windows

This checkout is already installed on the development laptop. Double-click **start.bat**, then open **http://127.0.0.1:8765**. Keep the terminal open while using the app; Ctrl+C stops it.

For a fresh checkout:

1. Install Python 3.12. No GPU, Node.js, account, API key or paid service is needed.
2. Double-click **setup.bat** for CPU, or **setup-gpu.bat** for a compatible NVIDIA GPU. Internet is needed once to download free dependencies and the approximately 378 MB acoustic model. PyTorch is also a substantial download (the tested Windows CUDA wheel is approximately 2.9 GB); allow several GB of free disk space.
3. Double-click **start.bat**, open the local address, select a demo variant and choose **Analyze comparison**.

Command-line equivalent:

```powershell
py -3.12 scripts/setup.py
.venv\Scripts\python.exe run.py
```

For NVIDIA support, use `py -3.12 scripts/setup.py --gpu`. The default launcher selects CUDA when available. Use **start-cpu.bat** to force CPU, or **start-gpu.bat** to request CUDA with fallback. If GPU memory is exhausted, the job retries on CPU and that server process remains on CPU until restarted. The interface and exported results report the actual device, precision, fallback reason and cached alignment use. There is no model training.

**Measured on this laptop:** RTX 3050 A, 4 GB, PyTorch 2.8.0/CUDA 12.6, float32. A 22.012-second reference aligned in a median 0.184 seconds on GPU versus 1.792 seconds on CPU across three warm, uncached runs (9.73x for alignment). The compared word boundaries and rounded confidence values agreed. Cold initialization took 15.49 seconds on GPU. A 60-second tiled-audio inference stress test completed on GPU with 1122.7 MiB peak allocated / 1566.0 MiB reserved memory. These are one-clip alignment measurements, not an end-to-end speed or population accuracy claim. See `reports/device-benchmark.json`; reproduce with `scripts/benchmark_devices.py` while the studio is stopped.

Python 3.11–3.13 is supported by the setup script; Python 3.12 on Windows is the tested target. On Linux/macOS run `python3 scripts/setup.py`, then `.venv/bin/python run.py`. Cross-platform execution has not been verified in this submission.

## What works

- Four real public-domain archive excerpts, with original controls and 36 generated, single-flaw variants.
- Upload two WAV/FLAC/OGG/MP3 recordings and their shared English transcript.
- Real pretrained wav2vec2 CTC word alignment, with transcript-agreement and alignment-quality gates.
- Three interpretable detectors: accelerated articulation, extra pauses, and local relative-energy drops.
- Paired playback, waveform navigation, selectable words, diagnostic contours and numeric evidence cards.
- Configurable rubric weights; downloadable JSON and a printable standalone HTML report.
- Local job progress, bounded queue, recoverable errors and session-result resume.

Keep each recording between 2 and 60 seconds, no larger than 20 MB, with one speaker and the exact same transcript (up to 150 words/1600 characters). Start with 20–30-second clips. Write numbers as spoken words. Noisy recordings, music, overlapping speakers and substantially different transcripts are outside the prototype's validated scope.

Measurements use the exact PCM16 samples served for playback. Over-range floating WAVs and very quiet accepted files receive a uniform gain adjustment before quantization; its factor is recorded in the exported `audio_processing` metadata. Relative-energy measurements remove recording-wide gain.

## Architecture

### Hosted deployment

The Vercel adapter uses the same analysis pipeline with CPU inference and synchronous requests. The browser prepares mono 16 kHz PCM16 audio to fit the 4.2 MB combined request limit. Uploaded audio is sent to the hosted server; temporary request files are removed when the request finishes normally, and results and playback remain in the browser. Closing or reloading the page discards the hosted result. There is no persistent cloud job store.

The interface identifies hosted processing before enabling analysis. For private processing entirely on your own computer, use the local launcher below. Local mode retains its existing job recovery and optional GPU support. Vercel Hobby quotas and cold starts can limit availability; this is a hackathon prototype rather than an unlimited production service.

See [deployment instructions](docs/DEPLOYMENT.md) for the CPU-only cloud dependencies, build-time model setup, memory checks and GitHub integration.

```
Browser audio + shared transcript
            |
      Local FastAPI queue
            |
  Local wav2vec2 emissions -> CTC word alignment
            |
  Actual word timing + NumPy/SciPy acoustic features
            |
  Versioned reference-relative rubric
            |
  Clickable evidence, independent playback, JSON/HTML report
```

The interface is buildless HTML/CSS/JavaScript. Local mode is served by Python; the hosted version serves static assets through Vercel's CDN. Neither mode uses external fonts, analytics or a paid model API. We use the pretrained acoustic model directly; there is no new foundation-model training and no LLM-generated score.

See [API contract](docs/API.md), [dataset card](docs/DATASET_CARD.md), [technical report](docs/TECHNICAL_REPORT.md), and [design context](DESIGN.md).

## Evaluation and reproducibility

```powershell
.venv\Scripts\python.exe -m pytest -q
node --test web/core.test.cjs web/diagnostics.test.cjs web/hosted.test.cjs
.venv\Scripts\python.exe scripts/evaluate.py
.venv\Scripts\python.exe scripts/verify.py
```

Node is optional and used only for developer frontend checks; the app does not need it. `scripts/evaluate.py` recomputes actual model alignments by default. `--use-cache` is explicit and recorded. The evaluation script uses the same alignment policy as the app and reads transformation labels only after inference. All descendants of a source recording remain together: JFK development, Reagan held-out test.

The machine-readable results are in `reports/evaluation.json`; the dataset card and technical report explain their limits. The original test-group aggregates were inspected before later engineering fixes, so the final run is a development rerun on source-disjoint groups, not a fresh untouched validation set. Controlled artificial errors establish intervention ground truth. They do **not** demonstrate accuracy for arbitrary humans, accents or speaking styles. Independent human-recording evaluation is not claimed.

Dependencies are pinned in `requirements.txt` and the tested Windows environment in `requirements-lock.txt`. PyTorch 2.8.0 is installed separately as CPU or CUDA 12.6, so installing the common lock cannot silently replace the selected backend. The acoustic model is pinned to `facebook/wav2vec2-base-960h` revision `22aad52d435eb6dbaf354bdad9b0da84ce7d6156`. Repeated outputs should agree within numerical tolerance in the tested environment; bitwise equivalence across devices or operating systems is not promised. Evaluation records actual device and source hashes.

## Dataset

`data/manifest.json` records every audio file, source offset, source group, split, transcript, transformation and temporal label. Public-domain sources are documented at the recording level in `data/sources.json`. Generated examples are visibly marked in the interface.

To reconstruct the variants from included reference clips:

```powershell
.venv\Scripts\python.exe scripts/build_dataset.py --variants-only
```

See the dataset card for the generator's exact command-line modes, source acquisition and attribution. Large full-length source recordings under `data/raw/` are excluded from the source package. The short reference/variant WAVs and labels are included.

## Interpretation and limitations

- The score measures this published rubric against the selected reference, not universal speaking quality, emotion, confidence or persuasiveness.
- A measured deviation can be an intentional rhetorical choice. Listen to the evidence before treating it as a flaw.
- Relative-energy changes can come from microphone movement or recording conditions.
- CTC word quality is a heuristic emission score, not calibrated assessment confidence. Incorrect/unclear transcripts may cause scoring to be withheld.
- Pitch, spectral centroid and MFCCs are diagnostics; they do not directly award quality points.
- This is a small, source-disjoint synthetic benchmark from two historical speakers. Generalization and independent human validation remain limited.
- The frozen pacing variants use a phase vocoder that also introduces audible/recognition artifacts. Low alignment quality causes many altered phrases to be skipped. This set does not establish sensitivity to natural rushed speech; see the per-type misses in the report.

## Privacy and local storage

In local mode, user recordings are processed on this computer and never sent to the model provider. The model is downloaded during setup only. Uploaded audio, transcript-derived results and reports are stored under ignored `.runtime/jobs/`; they expire after 24 hours and become unavailable on the next access, analysis or restart. They remain physically on disk until that cleanup executes. A stopped app cannot perform background deletion.

In hosted mode, the browser sends prepared audio and the transcript to Vercel for CPU processing. The application removes request-scoped temporary files after normal completion or handled errors; platform termination can interrupt cleanup, so this is not a secure-erasure guarantee. The application does not create persistent upload storage or public upload URLs. Vercel may retain ordinary operational request metadata under its own service policies. Demo archive recordings are public static assets.

Bundled public-domain demo alignment caches may remain in `.cache/alignments/`. User-upload alignments are not stored in that persistent cache. Browser storage contains only the last local job ID and interface preferences. Do not expose the server publicly; the launcher binds only to 127.0.0.1.

## Submission materials

- [Devpost project text](docs/DEVPOST.md)
- [Demo recording script](docs/DEMO_SCRIPT.md)
- [Technical report](docs/TECHNICAL_REPORT.md)
- [Six-page PDF report](output/pdf/SpeakTrace-technical-report.pdf)
- [Dataset card and provenance](docs/DATASET_CARD.md)
- [Human validation protocol](docs/HUMAN_VALIDATION.md)

Publishing the repository, recording/uploading the YouTube demo and adding real team members to Devpost are separate account actions. This local build does not claim those actions have happened.

To rebuild the PDF, install the optional `requirements-report.txt` dependencies and run `scripts/build_report.py`. To create a checked source/data archive, run `scripts/package_submission.py`. The archive excludes models, virtual environments, full raw source recordings and all runtime user uploads. Setup downloads the model separately.

## AI assistance and attribution

OpenAI Codex/ChatGPT assisted with track research, design, implementation, tests and documentation. Human entrants remain responsible for reviewing the work, understanding the algorithms and disclosing these tools in Devpost's **Built With** field. No AI-generated person or human-validation claim is included.

The pretrained model is Meta's wav2vec2-base-960h (Apache-2.0). Source archive recordings retain their documented public-domain status. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) and dataset provenance. SpeakTrace's original code is MIT licensed.
