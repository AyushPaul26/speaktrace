# Frontend verification

The studio is buildless HTML/CSS/JavaScript. `web/core.js` contains deterministic validation, timing, weight and media URL rules. `web/core.test.cjs` verifies real edge cases for those rules. `web/check_ui.py` checks markup associations, documented token generation/drift, required accessibility styles and selected async safety invariants. These are static/logic checks, not proof of rendered accessibility.

## Browser handoff

Browser QA was delegated to the frontend worker by the root orchestrator and exercised against the real server at http://127.0.0.1:8765. The initial handoff checklist was:

1. Initial library loading, actual no-result state and library recovery.
2. A real archive demo, its clean control and a generated variant. Verify no displayed score precedes a real job result.
3. Real upload with both recordings, transcript validation, server failure and preserved inputs.
4. Paired playback, word seeks, selected evidence bands and interval replay. Confirm each track uses its own elapsed-time coordinates.
5. Rapid demo/variant selection while a job is pending; late responses must not overwrite the new selection.
6. Stop watching and Resume progress. Stopping the browser watcher must never claim server computation stopped.
7. Null/withheld score, no-findings state, nonempty warnings, unplayable/expired media.
8. JSON download and printable report.
9. Keyboard navigation, native radio arrow keys, range arrows, first validation-error focus and modal Escape/focus return.
10. A narrow viewport, long names/transcript, reduced motion and global scrollbar style.

The draft is held only in memory and preserved on in-app mode changes. A browser-unload prompt guards unsubmitted user input. There is no authentication, paid request, destructive data operation, remote search, date picker, authored select, dark theme or multi-locale promise in this scope.

## Design decision review

The early concept of score-led dashboard cards was rejected in favor of measured paired tracks. The resulting layout makes the subject itself the focal element: archive reference and participant waveform, their own time axes, word-level evidence. Sidebar examples and the right-hand rubric remain quiet. Tokens are generated from DESIGN.md rather than copied between systems. With no existing sibling screen, the reference/participant track pair and demo/upload flows are the consistency comparators.

## Actual results

- `node --check web/app.js` and `node --check web/core.js`: passed.
- `node --test web/core.test.cjs`: 7 passed, 0 failed.
- `.venv/Scripts/python.exe web/check_ui.py`: passed; generated token consistency and static markup checks.
- Strict `audit_project.py`: zero errors, warnings or unresolved findings; `reports/frontend-premium-audit.json`.
- Official `npx --yes --cache ./runtime/npm-cache -p @google/design.md designmd lint DESIGN.md`: could not run because registry.npmjs.org DNS returned ENOTFOUND. No frontend dependency was installed. Local generator verifies frontmatter-to-CSS drift.
- Readable-text contrast was checked numerically. The primary teal was darkened to `#08766f` after its original selected-tint contrast was below 4.5:1. Muted text on the pale background is 4.63:1; navy on white is 13.82:1.
- Real browser: the library loaded four archive recordings. Initial no-score, disabled playback/export and empty-evidence states were inspected.
- Initial core 1.0 browser session: the JFK severe-pause demo finished after Stop watching → Resume progress with 100/100, no findings and a skipped-region warning. This measurement issue was reported to the acoustic workers. The later core 1.1 smoke result below verifies the corrected pause detection.
- Real browser upload: JFK reference versus generated severe-energy audio completed in 3.96 seconds with a 98/100 result and one energy interval. The inspector showed -1.94 versus -10.3 dB. Both waveforms, selected bands, typed finding labels and word highlights were visible.
- Real browser: excerpt playback started at the selected participant interval and stopped near its endpoint; a non-flagged word sought reference and participant to their own times (18.6118 and 18.5918 seconds).
- Real browser: JSON download succeeded and the printable HTML report opened in another tab with matching score, evidence, transcript and rubric.
- Real browser: empty-upload submit focused the reference field with associated inline errors. A numeral transcript produced correction guidance. A nonempty corrupt WAV reached server validation and showed “Could not decode this audio…” while keeping both file names and transcript.
- Real browser: native range Home keys set all three weights to zero, disabling analysis; Reset restored 40/35/25. The methodology modal opened, Escape closed it, and focus returned to its trigger.
- Real browser: 390×844 narrow viewport had document width 380 and no horizontal overflow. The global computed scrollbar color was `rgb(165, 184, 196) rgb(238, 243, 245)`. Result screenshots are in `reports/studio-desktop.jpg`; error evidence is in `reports/studio-upload-error.jpg`.
- Real browser: a new JFK pacing analysis was immediately superseded by selecting the second recording. The new selection remained in no-result state with its correct transcript; late-result rejection was checked after allowing server work to finish.

No screen-reader session, touch hardware, forced-colors emulation, offline network interception, complete 200% zoom matrix, or official designmd lint is claimed. Reduced-motion/forced-colors rules and null-score handling have static coverage; backend tests cover unreliable scoring independently. Browser-only console output had no JavaScript errors during the successful upload flow.

## Subsequent diagnostics and device-metadata revision

The root added word-indexed energy, pitch and spectral-centroid contours, an expandable exact-values table, and device metadata for CPU/CUDA/mixed alignment. DESIGN.md and UX-CONTRACT.md now record their ownership, missing-value policy, separate word-index/time axes, keyboard table alternative, bounded table scrolling, actual device labels and cache-aware total timing. The revised manifest runs the diagnostics syntax and logic checks alongside the existing frontend checks.

The resumed CUA runtime was unavailable: it had no retained browser/tab, and the supported `createBrowserTab('iab', ...)` call returned “Browser is not available: iab.” The orchestrator subsequently supplied an installed Playwright/Chrome path for a project-local functional test. `scripts/browser_smoke.cjs` uses a fresh nonpersistent headless Chrome context, never a personal profile. Environment variables `PLAYWRIGHT_MODULE`, `CHROME_PATH` and `SPEAKTRACE_URL` allow installed-runtime overrides; no frontend dependency or package installation is required. The URL is restricted to loopback. Local socket access required an authorized escalation.

`node scripts/browser_smoke.cjs` passed on 2026-10-13 at 11:36 UTC against the real CPU server. The preserved `reports/browser-smoke-cpu.json` records job IDs, timings, exact checks, console errors and test controls. The severe-pause demo returned a measured 1.79-second excess pause and score 94.5 with rubric reference-relative-1.1.0. Energy, Pitch and Spectrum each rendered two contours and 41 table rows; exact table values matched the per-word feature reducer. A table selection sought reference to 14.169 seconds and participant to 15.9694 seconds, returning focus to word 25. At 390×844 the document width was 380px with no horizontal overflow; toggles/table seeking worked and the coverage caption wrapped. Both Stop watching → edit transcript and Stop watching → change file invalidated Resume and rejected eventual old-job results. The device badge truthfully said local CPU. There were zero page or console errors.

For these two race regressions only, the harness held GET job-status requests before forwarding, then released them after input edits. All POSTs created real jobs and their completed results were retrieved independently. No scores, findings, feature arrays or analysis responses were fabricated. Fresh screenshots are `reports/studio-final.jpg` and `reports/studio-final-narrow.jpg`; earlier screenshots remain historical evidence.

The final replay-context revision adds 0.25 seconds around each measured interval, clipped at recording edges. Its two new tests first failed for the missing helper, then passed after implementation; all 12 core/diagnostics tests passed. The full smoke was rerun after the service restart and passed at 11:42 UTC; `reports/browser-smoke.json` is the current report. Both context controls played and stopped at their expanded endpoints: reference 7.7351–8.2351 seconds and participant 7.86469–10.15469 seconds. The exact pause measurements remained 0 and 1.79 seconds. All diagnostic, stale-job, narrow and no-error checks passed again. The two final screenshots were regenerated and visually inspected with context controls visible at desktop and narrow widths.

The final runtime reported auto-selected CUDA on NVIDIA GeForce RTX 3050 A Laptop GPU, Torch 2.8.0+cu126. The first analysis response recorded both alignments as CUDA with cached=false; the screenshot's later result correctly disclosed cached alignment. Health and result device labels were checked separately. This is evidence of the device reporting and observed execution path, not a hardware speed benchmark. Acoustic feature extraction remained CPU work. Final syntax checks passed, static checks passed with 27 tokens and 88 IDs, and the strict premium audit reported zero findings. Official designmd lint and the extended accessibility/device matrix remain limited as described above.

## Hosted production verification

On 2026-10-13 at 18:45 UTC, `scripts/hosted_smoke.cjs` passed 11 checks against https://speaktrace-amber.vercel.app in a fresh Chrome context. Both the demo and upload sent real requests and performed uncached CPU inference. Each returned score 94.5 and the expected 1.79-second extra pause. The browser verified reference and participant context playback, separate transcript seeking, a 390px layout, upfront cloud privacy disclosure, and JSON/HTML exports for both modes. A read-only observer hashed the actual multipart WAV bytes before forwarding the original fetch arguments unchanged; both hashes matched browser playback. No analysis responses were intercepted or fabricated. The run had no page, console or unexpected network errors. Expected media cancellations during seeking or changing recordings are recorded separately.

The successful report and visually inspected screenshot are `reports/hosted-deployment.json` and `reports/hosted-deployment.jpg`. Earlier harness-only failures are retained and explained in the deployment guide. Current automated verification passes 124 Python tests and 20 JavaScript tests; static markup has 27 tokens and 96 IDs. These checks establish the observed deployment behavior, not independent natural-speech accuracy or load capacity.
