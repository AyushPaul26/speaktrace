# SpeakTrace UI contract

Authoritative sources: `docs/API.md`, `docs/superpowers/specs/2026-10-13-speaktrace.md`. This is a single local tool without accounts, billing, permissions, destructive actions or external publication. Retention and inference privacy follow the API contract; UI text must not invent another lifecycle.

## Canonical UI Map

| Capability | Canonical owner | Source of truth | Allowed variants | Verification |
|---|---|---|---|---|
| Form | web/app.js validateUpload / setFieldError | API.md | demo, upload | core tests, browser flow |
| Scrollbar | web/styles.css global baseline | DESIGN.md | normal, forced-colors | static checker, browser |
| Toast | web/app.js announce / setNotice | this contract | polite status, persistent inline error | static checker, browser |
| Dialog | web/index.html methodology-dialog | this contract | read-only native dialog | keyboard browser QA |
| Playback | web/app.js renderTrack / selectFinding | API.md | reference, participant | browser audio + interval selection |
| Job | web/app.js startAnalysis / pollJob | API.md | demo, upload | API integration, stale-state browser QA |
| Acoustic diagnostics | web/diagnostics.js valuesAtWords / render | API.md features + DESIGN.md | energy, pitch, spectral centroid | diagnostics.test.cjs; chart/table browser QA |
| Device reporting | web/app.js deviceLabel / loadHealth / renderSummary | API.md compute metadata | CPU, CUDA, mixed | server device tests; runtime UI verification |

## Shared behavior

- The demo list is bounded by the local manifest, so render all entries. No search, pagination or select/listbox exists.
- Changing demo, variant or mode cancels/invalidates client polling and clears the old result. It does not pretend to cancel server computation. A generation token prevents stale completions from taking over a new selection.
- Editing an upload file or transcript also invalidates a retained job after Stop watching. Resume progress is available only while the current inputs still identify that job; edited inputs must never resume and display an older comparison.
- Upload fields survive switching to demos and all network/server failures. File content and transcript are memory-only. The browser unload guard applies while a recording draft is unsubmitted. In-app mode changes preserve the draft and need no confirmation.
- Client validation associates errors with fields and focuses the first invalid field. Server validation is authoritative. A shared novalidate form prevents native validation bubbles. A valid submit disables repeat submission and rubric changes until settled.
- Pessimistic analysis transitions: ready → uploading/queued → named local model stages → result or recoverable error. Stage progress comes from the server and is labelled as stages, never remaining time. No optimistic scores. Failed polling can resume the known job; POST requests never auto-retry.
- GET requests have a bounded timeout. Polling retries safe transient failures three times then offers Resume. Long jobs offer Stop watching, which stops local polling while explaining that server work continues. Selection change or a newer operation aborts older requests.
- Result scores come only from the response. Null means withheld. Warning text remains visible. A clean comparison with no findings is a valid result and gets its own empty evidence state.
- Both players share one renderer. Only one plays at a time. Selecting a finding seeks both recordings to their own matching interval. Evidence replay adds 0.25 seconds of context on both sides using core.playbackInterval, clipped to the recording duration, and pauses at that expanded endpoint. Buttons label the playback as context and display the expanded range; measured bounds and chart bands remain exact. Word selection maps by word index and uses each recording's word times. Native sliders offer keyboard seek; waveform pointer seeking has the same meaning.
- Acoustic feature toggles preserve the current result and switch only the diagnostic dimension. The chart aligns by transcript word index and computes per-word medians from each recording's real feature times. Missing/unvoiced/weak values remain gaps, not zero. Reference and participant have different line styles as well as colors. Chart points and native table-word buttons delegate to the shared transcript-word selection behavior.
- The diagnostics values table renders all available transcript words, bounded by the 150-word input limit. Its 240px scroll region belongs to the table only. The surrounding form and page retain document scrolling. No table selection, sorting, pagination or ARIA grid behavior is implied.
- Device labels come from server metadata, never hardware assumptions. Current health and result alignment device can legitimately differ after fallback or cache use. Report total elapsed computation with cache disclosure; CPU features and comparison must not be described as GPU work. GPU execution and performance are claimed only after an actual GPU run is verified.
- Exports remain disabled until there is a valid result. JSON is downloaded from the returned result id; printable HTML opens its same-origin report in a new tab. User-generated strings use textContent or DOM construction, never HTML parsing.
- Keyboard order follows the document. Native radio/slider/file semantics are preserved. Dialogs use showModal, a close button, Escape and focus restoration. Status changes are announced politely without moving focus.
- Single English locale with Intl.NumberFormat. Dates show the viewer's local timezone only if present. Reduced motion, high contrast and narrow layout preserve all actions.

## Flow ledger

| Operation | Pending | Success | Failure recovery | Source |
|---|---|---|---|---|
| Load library | reserved status region | choose first real demo | retry library; upload still usable | GET /api/demos |
| Analyze demo | disable duplicate; named progress | same workspace result | keep selection, retry | POST demo analysis |
| Analyze uploads | preserve names/transcript; busy action | same workspace result | inline validation, preserved draft | POST /api/analyze |
| Watch job | bounded cancellable polls | render only current generation | resume known job | GET /api/jobs/id |
| Select evidence | immediate shared selection | inspector + both seeks | media error shown next to player | Analysis contract |
| Switch acoustic feature | immediate local recomputation | labelled contour and exact-value table | absent values remain gaps | Recording.features contract |
| Export report | browser download/navigation | full JSON/printable report | server-owned response | report endpoints |

## Verification scope

`node --check web/app.js`, `node --check web/diagnostics.js`, `node --test web/core.test.cjs web/diagnostics.test.cjs`, `python web/check_ui.py`, and the strict premium audit are static/logic evidence. `node scripts/browser_smoke.cjs` runs repeatable browser QA against the real local API, including diagnostics, desktop/narrow, context replay and stopped-job edits. It requires the installed model, demo manifest, Playwright and Chrome; environment overrides are documented in the script. Static checks never stand in for runtime evidence. See docs/frontend-verification.md and reports/browser-smoke.json for the precise verified revision and remaining limits.
