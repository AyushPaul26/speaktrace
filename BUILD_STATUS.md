# SpeakTrace build ledger

User approved the Track C concept and requested an end-to-end, free build on 2026-10-13. They subsequently clarified that the laptop has an RTX 3050 with 4 GB VRAM; hardware inspection identified the RTX 3050 A Laptop GPU. CPU and GPU inference are verified. Existing workspace documents are left untouched; project is isolated in speaktrace/.

## Decisions

- Use a buildless browser UI served by FastAPI instead of Streamlit, enabling precise audio/timeline interaction without Node installation.
- Use pretrained wav2vec2 directly through Transformers rather than WhisperX's complete transcription/diarization stack; the supplied transcript makes those extra models unnecessary. Actual CTC alignment remains required.
- Local setup keeps its environment and model in this project. Hosted setup installs CPU dependencies and downloads the model on Vercel's build machine. No paid services or training. Optional local GPU inference uses the same pretrained model and reports actual backend provenance.
- Prepare source/dataset/docs locally; public GitHub/YouTube/Devpost actions require actual user account/team information and must never be claimed as done without evidence.

## Progress

- Read all contest PDFs in preceding research and verified deadline/rules.
- Wrote approved concept, API contract, implementation plan.
- CPU installation, model download, real demo/upload and browser interaction completed.
- Four public-domain references and 40 variants are included with checksums, source-disjoint groups and temporal labels. The initial benchmark is preserved; its phase-vocoder pacing confound is documented.
- Core confidence/quiet-gap improvements, GPU support and final evaluation are complete. The source-disjoint synthetic test group has 7 true positives, 1 false positive and 11 misses: all six pause edits were detected, but energy and pacing sensitivity remain limited. This is a development rerun, not untouched validation.
- Latest automated verification: 124 Python tests, 20 JavaScript tests, static UI checks, syntax and compilation passed. The installed local dependencies also passed pip check.
- The real GPU browser smoke passed 13 checks, including evidence replay, diagnostics, separate word seeking, narrow layout and stale-job handling, with no page or console errors.
- Measured warm alignment on a 22.012-second clip: CPU median 1.7921 seconds, GPU median 0.1842 seconds (9.73x). A separate 60-second inference memory stress test peaked at 1122.7 MiB allocated. These are alignment measurements, not whole-app speed or accuracy claims.
- The six-page PDF report was generated and every page visually checked. Source/data packaging, Devpost text and a video narration script are prepared. No participant study is claimed.
- The public repository [AyushPaul26/speaktrace](https://github.com/AyushPaul26/speaktrace) is published on `main`. Anonymous GitHub access and the reviewed commit were verified; installed environments, models, caches and private runtime uploads are excluded.
- The Vercel adapter uses synchronous CPU analysis, request-scoped temporary files and a 30-second limit per recording. Local mode retains its 60-second limit. Live deployment verification is pending; a build or reserved production address alone is not evidence that hosted analysis works.

## Remaining submission actions

The entrant must review the results, supply real team/account details, record and upload the 3–10 minute demo, and submit through Devpost. The public repository is already available. The project includes submission copy and a recording script. Human validation and improved natural-speech pacing/energy evaluation remain future research rather than completed evidence.
