# Publishing SpeakTrace

The public source repository is https://github.com/AyushPaul26/speaktrace and the production site is https://speaktrace-amber.vercel.app. The Vercel project is `speaktrace` in the owner's Hobby workspace and is connected to this repository. Deployments build on Vercel; the laptop does not need another Python environment or another model download.

## Two execution modes

- Local: `start.bat` runs the original queued API, optional NVIDIA inference, local recordings and job recovery.
- Hosted: `api/index.py` runs a synchronous CPU API with a 30-second limit per recording. The browser converts uploaded recordings to mono 16 kHz PCM16 WAV, sends at most 4.2 MB per request and retains those exact WAVs for playback through temporary browser URLs. Reports are exported from the current browser result. Local mode retains its 60-second limit.

The frontend reads `/api/health` to select the correct transport and privacy text. Hosted processing sends audio to the cloud. Local processing stays on the user's machine. No paid model API is used.

## Build and deployment

1. Push the reviewed code to `main` in GitHub. The connected Vercel project builds that commit.
2. Vercel uses Python 3.12 and the dependencies in `pyproject.toml`. PyTorch is resolved from the explicit CPU-only package index, avoiding CUDA downloads.
3. `scripts/build_hosted.py` downloads the existing pinned acoustic model into the remote build directory.
4. `scripts/probe_hosted_memory.py` runs isolated, complete CPU analyses on a real short pair and a 30-second tiled stress pair. It rejects a build exceeding 1900 MiB peak process RSS or 300 seconds per worker. Build-host timings are not guarantees of deployed runtime speed; public inference must also be tested.
5. FastAPI mounts the source `web/`, `data/references/` and `data/variants/` directories at their matching URL prefixes. Vercel's static integration promotes these public assets to its CDN (`tool.vercel.fastapi.static.cdn = true`) while retaining them in the function for demo inference and fallback serving. The model remains in the Python function bundle. The root HTML page is served by the app.

The entrypoint is `api.index:app`; `vercel.json` configures its 300-second limit and includes `.models/**`. Large Functions beta is enabled through `VERCEL_SUPPORT_LARGE_FUNCTIONS=1`; the project requires Fluid compute. Neither `.venv`, `.cache`, `.runtime`, raw full-length archive downloads nor credentials are uploaded.

## Platform limits and operating scope

At preparation time, Vercel documents a 5 GB large-function beta, with Hobby limits of 2 GB RAM, one vCPU, 300 seconds per invocation and 4.5 MB request/response bodies. The application imposes a smaller 4.2 MB request limit. Hobby includes usage quotas; exhausting them can interrupt the demo. No plan upgrade or paid add-on is required by this configuration.

Sources: https://vercel.com/docs/functions/limitations and https://vercel.com/docs/frameworks/backend/fastapi .

The API accepts only same-origin browser POSTs and permits one analysis at a time per function instance. That is a resource guard, not user authentication or a global rate limit. The public demo is intended for light hackathon use.

The first remote build completed a 60-second stress analysis but exceeded the project's 1900 MiB memory gate (1928.488 MiB). The gate rejected that build. Hosted recordings were subsequently limited to 30 seconds to leave room within Hobby's 2 GB runtime; the original local limit is unchanged. The initial measurements are recorded in `reports/hosted-memory-initial.json`.

## Verification

Run `scripts/verify.py` with the local virtual environment. `web/hosted.browser.test.cjs` tests actual browser audio conversion and transport against explicitly marked fixture responses; it does not replace live inference verification. The deployed site must separately complete an actual demo and upload analysis, play the returned evidence and export a report.

That live check passed all 11 steps on 2026-10-13 at 18:45 UTC against `https://speaktrace-amber.vercel.app`, running application commit `fc6bedf`. The uncached public demo took 13.613 seconds end to end and the upload took 13.495 seconds. Both used the pinned CPU model and measured the expected 1.79-second extra pause, with score 94.5. These observed timings are not a service-level guarantee. Static JavaScript, CSS and WAV requests also returned HTTP 200 with CDN cache hits.

`reports/hosted-deployment.json` records the successful real responses and browser checks; `reports/hosted-deployment.jpg` shows the uploaded comparison. Run `scripts/hosted_smoke.cjs` with `SPEAKTRACE_DEPLOYMENT_URL` explicitly set to the project URL to reproduce the check. The two `*-harness-failure.json` files preserve earlier incomplete checks: analysis succeeded, but the harness incorrectly expected Chromium to expose a binary request body and expected archive provenance on user uploads. Those assumptions were corrected before the successful full rerun; no inference responses were replaced.

The hosted adapter retains the existing model revision and comparison rubric. The included technical PDF describes the original local evaluation; deployment changes do not establish new speech-assessment accuracy. Pacing/energy limitations and lack of independent human validation still apply.
