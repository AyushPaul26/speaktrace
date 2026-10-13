/* Live hosted smoke check: two real analyses, no fixture or intercepted replies.
 * Uses only included public-domain demo audio, never personal browser profiles.
 * Set SPEAKTRACE_DEPLOYMENT_URL to this project's Vercel URL or loopback.
 */
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const os = require('node:os');
const { createHash } = require('node:crypto');
const ROOT = path.resolve(__dirname, '..');
const BASE = process.env.SPEAKTRACE_DEPLOYMENT_URL;
assert(BASE, 'Set SPEAKTRACE_DEPLOYMENT_URL explicitly before running live checks.');
const target = new URL(BASE);
const loopback = ['127.0.0.1', 'localhost', '[::1]'].includes(target.hostname);
assert(!target.username && !target.password && !target.search && !target.hash, 'Use a plain project URL, without credentials or tokens.');
assert(loopback || (target.protocol === 'https:' && /^speaktrace(?:-[a-z0-9]+)*\.vercel\.app$/i.test(target.hostname)), 'Only the SpeakTrace Vercel project or loopback may be tested.');
const ORIGIN = target.origin;
const { playbackInterval, time } = require('../web/core.js');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || path.join(os.homedir(), '.cache', 'codex-runtimes', 'codex-primary-runtime', 'dependencies', 'node', 'node_modules', 'playwright'));
const chrome = process.env.CHROME_PATH || path.join(process.env.ProgramFiles || 'C:/Program Files', 'Google', 'Chrome', 'Application', 'chrome.exe');
const report = {
  started_at: new Date().toISOString(), target: ORIGIN, passed: false,
  browser: 'Installed headless Chrome, fresh nonpersistent context, no personal browser profile',
  method: 'Real unmodified network responses. At most two analysis POSTs: public-domain JFK severe-pause demo, then the same included pair through upload UI.',
  upload_observation: 'A read-only in-page observer hashes the actual multipart Blob before forwarding the original fetch arguments unchanged. No analysis response, score, finding, or request body is replaced.',
  steps: [], analyses: {}, page_errors: [], console_errors: [], request_failures: [], expected_media_cancellations: [], artifacts: [],
  limitations: ['Functional deployment smoke check, not a load test or independent model-quality evaluation.'],
};
let browser, context, page;
function pass(name, evidence = {}) { report.steps.push({ name, passed: true, ...evidence }); console.log(`PASS ${name}`); }
function digest(bytes) { return createHash('sha256').update(bytes).digest('hex'); }
function resultEvidence(result, seconds) {
  return { id: result.id, mode: result.mode, score: result.summary.score, seconds, rubric: result.rubric.version, compute: result.compute, audio_processing: result.audio_processing, findings: result.findings.map(item => ({ type: item.type, start: item.start, end: item.end, reference_start: item.reference_start, reference_end: item.reference_end, evidence: item.evidence })) };
}
function verifyPause(result) {
  assert.equal(result.compute.device, 'cpu', 'Hosted analysis must report actual CPU execution');
  assert.equal(result.compute.cached_alignment, false, 'Hosted comparison must perform fresh alignment');
  const pause = result.findings.find(item => item.type === 'pauses');
  assert(pause, 'Included severe pause must produce a measured pause finding');
  const excess = pause.evidence.participant - pause.evidence.reference;
  assert(Math.abs(excess - 1.79) < .15, `Expected approximately 1.79 s extra pause, got ${excess}`);
  assert(Math.abs(result.summary.score - 94.5) < 1, `Expected approximately 94.5 score, got ${result.summary.score}`);
  return pause;
}
async function analyze(endpoint) {
  const responsePromise = page.waitForResponse(response => new URL(response.url()).pathname === endpoint && response.request().method() === 'POST', { timeout: 340000 });
  const started = Date.now(); await page.locator('#analyze-button').click();
  const response = await responsePromise;
  assert.equal(response.status(), 200, `Analysis returned HTTP ${response.status()}: ${(await response.text()).slice(0, 500)}`);
  const result = await response.json();
  await page.locator('#edit-comparison').waitFor({ state: 'visible', timeout: 15000 });
  return { result, response, seconds: (Date.now() - started) / 1000 };
}
async function checkExports(label) {
  const downloadPromise = page.waitForEvent('download'); await page.locator('#download-json').click(); const download = await downloadPromise;
  const stream = await download.createReadStream(); const chunks = []; for await (const chunk of stream) chunks.push(chunk);
  const exported = JSON.parse(Buffer.concat(chunks).toString('utf8'));
  assert(exported.id && exported.rubric && exported.compute);
  if (exported.mode === 'demo') assert(exported.provenance, 'Bundled demo exports include archive provenance');
  else assert(exported.audio_processing?.browser_preparation, 'Upload exports include browser preparation provenance');
  for (const kind of ['reference', 'participant']) assert(!String(exported[kind].url).startsWith('blob:'), 'JSON must omit temporary playback handles');
  const popupPromise = page.waitForEvent('popup'); await page.locator('#print-report').click(); const popup = await popupPromise;
  await popup.waitForLoadState(); const text = await popup.locator('body').innerText();
  assert(text.includes(exported.id)); assert(text.includes('Hosted speech comparison')); assert(text.includes('Rubric scores')); assert(text.includes('Evidence'));
  await popup.close(); pass(`${label}: stateless JSON and printable HTML exports`, { id: exported.id, has_browser_preparation: Boolean(exported.audio_processing?.browser_preparation) });
  return exported;
}
async function main() {
  await fs.mkdir(path.join(ROOT, 'reports'), { recursive: true });
  browser = await chromium.launch({ headless: true, executablePath: chrome, args: ['--no-first-run', '--disable-background-networking'] });
  context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, reducedMotion: 'reduce', acceptDownloads: true });
  page = await context.newPage(); page.setDefaultTimeout(20000);
  page.on('pageerror', error => report.page_errors.push(error.message));
  page.on('console', item => { if (item.type() === 'error') report.console_errors.push(item.text()); });
  page.on('requestfailed', request => {
    const url = new URL(request.url()), reason = request.failure()?.errorText;
    const expectedMediaCancellation = reason === 'net::ERR_ABORTED' && request.resourceType() === 'media' && (url.protocol === 'blob:' || url.pathname.startsWith('/data/'));
    (expectedMediaCancellation ? report.expected_media_cancellations : report.request_failures).push({ path: url.protocol === 'blob:' ? '[browser playback blob]' : url.pathname, reason });
  });
  const started = Date.now(), health = await context.request.get(`${ORIGIN}/api/health`, { timeout: 120000 });
  assert(health.ok(), `Health returned HTTP ${health.status()}`); report.health = await health.json();
  assert.equal(report.health.deployment, 'vercel'); assert.equal(report.health.synchronous, true); assert.equal(report.health.device, 'cpu'); assert.equal(report.health.model_ready, true);
  assert.equal(report.health.max_seconds, 30, 'Hosted duration limit should preserve room within cloud memory limits');
  pass('Hosted health reports installed CPU model and synchronous API', { seconds: (Date.now() - started) / 1000 });
  for (const asset of ['/', '/web/hosted.js', '/web/app.js', '/web/styles.css', '/data/references/jfk-welcome.wav', '/data/variants/jfk-welcome/pauses-severe.wav']) {
    const response = await context.request.get(`${ORIGIN}${asset}`, { timeout: 90000 }); assert(response.ok(), `${asset} returned HTTP ${response.status()}`);
  }
  pass('Public studio, scripts, styles and both archive WAVs are reachable');
  await page.goto(ORIGIN, { waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() => document.querySelector('#device-badge').textContent === 'CPU · CLOUD', {}, { timeout: 120000 });
  assert.equal(await page.locator('#deployment-label').innerText(), 'CLOUD STUDIO');
  assert.match(await page.locator('#privacy-summary').innerText(), /sent to this Vercel service/);
  await page.locator('.demo-card').filter({ hasText: 'A university welcome' }).click();
  await page.getByRole('radio', { name: 'Generated severe pauses', exact: true }).check();
  const demo = await analyze('/api/hosted/demos/jfk-welcome/analyze');
  report.analyses.demo = resultEvidence(demo.result, demo.seconds); const pause = verifyPause(demo.result);
  pass('Real hosted demo performs fresh CPU alignment and displays measured pause', { seconds: demo.seconds, score: demo.result.summary.score, excess_seconds: pause.evidence.participant - pause.evidence.reference });
  await page.locator(`[data-finding="${pause.id}"]`).click();
  for (const kind of ['reference', 'participant']) {
    const interval = playbackInterval(pause, kind, demo.result[kind].duration), button = page.getByRole('button', { name: new RegExp(`^Play ${kind} context`) });
    assert((await button.innerText()).includes(`${time(interval.start, true)}–${time(interval.end, true)}`)); await button.click();
    await page.waitForFunction(({ kind, start }) => { const audio = document.querySelector(`#${kind}-track audio`); return !audio.paused && audio.currentTime >= start; }, { kind, start: interval.start });
    await page.waitForFunction(({ kind, end }) => { const audio = document.querySelector(`#${kind}-track audio`); return audio.paused && audio.currentTime >= end - .06 && audio.currentTime <= end + .4; }, { kind, end: interval.end });
    pass(`Demo ${kind} evidence playback honors actual interval`, interval);
  }
  const wordIndex = Math.min(25, demo.result.participant.words.length - 1); await page.locator(`#word-${wordIndex}`).click();
  const expected = { reference: demo.result.reference.words[wordIndex].start, participant: demo.result.participant.words[wordIndex].start };
  await page.waitForFunction(value => Math.abs(document.querySelector('#reference-track audio').currentTime - value.reference) < .06 && Math.abs(document.querySelector('#participant-track audio').currentTime - value.participant) < .06, expected);
  pass('Transcript seeks each recording to its own word timestamp', expected);
  await checkExports('Demo');
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole('button', { name: 'Pitch', exact: true }).click(); assert.equal(await page.locator('[data-diagnostic="pitch_st"]').getAttribute('aria-pressed'), 'true');
  const narrow = await page.evaluate(() => ({ width: innerWidth, scrollWidth: document.documentElement.scrollWidth })); assert(narrow.scrollWidth <= narrow.width);
  pass('390 px layout has no horizontal overflow and acoustic toggle works', narrow);
  await page.setViewportSize({ width: 1440, height: 1000 });
  const manifest = JSON.parse(await fs.readFile(path.join(ROOT, 'data/manifest.json'), 'utf8')), reference = manifest.references.find(item => item.id === 'jfk-welcome');
  const variant = reference.variants.find(item => item.id === 'pauses-severe');
  await page.locator('#upload-mode').click(); assert.equal(await page.locator('#privacy-notice').isVisible(), true);
  assert.match(await page.locator('#privacy-notice').innerText(), /sends both recordings and the transcript/);
  await page.locator('#reference-file').setInputFiles(path.join(ROOT, reference.audio)); await page.locator('#participant-file').setInputFiles(path.join(ROOT, variant.audio)); await page.locator('#transcript-input').fill(reference.transcript);
  // Chromium's request.postDataBuffer() omits binary Blob bodies. Observe the
  // submitted body in-page without modifying it, routing it, or faking replies.
  await page.evaluate(() => {
    const originalFetch = window.fetch;
    window.fetch = async function (input, options) {
      if (input === '/api/hosted/analyze' && options?.method === 'POST') {
        const body = options.body;
        if (!(body instanceof Blob)) throw new Error('Smoke test expected the prepared multipart Blob.');
        const form = await new Response(body, { headers: options.headers }).formData();
        const recordings = {};
        for (const kind of ['reference', 'participant']) {
          const bytes = await form.get(kind).arrayBuffer(), view = new DataView(bytes);
          const hash = Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', bytes)), value => value.toString(16).padStart(2, '0')).join('');
          recordings[kind] = { bytes: bytes.byteLength, sha256: hash, format: view.getUint16(20, true), channels: view.getUint16(22, true), sample_rate: view.getUint32(24, true), bits: view.getUint16(34, true) };
        }
        window.__speaktraceObservedUpload = { body_bytes: body.size, recordings };
      }
      return originalFetch.apply(this, arguments);
    };
  });
  const upload = await analyze('/api/hosted/analyze'); report.analyses.upload = resultEvidence(upload.result, upload.seconds); verifyPause(upload.result);
  const observed = await page.evaluate(() => window.__speaktraceObservedUpload); assert(observed && observed.body_bytes < 4200000);
  for (const kind of ['reference', 'participant']) {
    const uploaded = observed.recordings[kind]; assert.equal(uploaded.format, 1); assert.equal(uploaded.channels, 1); assert.equal(uploaded.sample_rate, 16000); assert.equal(uploaded.bits, 16);
    const audioURL = await page.locator(`#${kind}-track audio`).getAttribute('src'); assert(audioURL.startsWith('blob:'));
    const playback = Buffer.from(await page.locator(`#${kind}-track audio`).evaluate(async audio => Array.from(new Uint8Array(await (await fetch(audio.src)).arrayBuffer())))); assert.equal(playback.length, uploaded.bytes); assert.equal(digest(playback), uploaded.sha256);
    report.analyses.upload[`${kind}_pcm`] = { bytes: uploaded.bytes, sha256: uploaded.sha256, playback_identical: true };
  }
  pass('Actual upload converts to bounded canonical WAVs with byte-identical playback', { body_bytes: observed.body_bytes, seconds: upload.seconds, score: upload.result.summary.score });
  const exportedUpload = await checkExports('Upload'); assert.equal(exportedUpload.audio_processing.browser_preparation.reference.encoding, 'WAV PCM16 mono');
  assert.match(await page.locator('#result-meta').innerText(), /CPU alignment/); assert(!(await page.locator('#result-meta').innerText()).includes('includes cached alignment'));
  await page.locator('.finding').filter({ hasText: /pause/i }).first().click(); await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: path.join(ROOT, 'reports/hosted-deployment.jpg'), fullPage: true, type: 'jpeg', quality: 85 }); report.artifacts.push('reports/hosted-deployment.jpg');
  assert.deepEqual(report.page_errors, []); assert.deepEqual(report.console_errors, []); assert.deepEqual(report.request_failures, []);
  pass('No browser page errors, console errors or failed network requests'); report.passed = true;
}
main().catch(async error => {
  report.error = error.stack || String(error); console.error(report.error); process.exitCode = 1;
  if (page) { try { await page.screenshot({ path: path.join(ROOT, 'reports/hosted-deployment-failure.jpg'), fullPage: true }); report.artifacts.push('reports/hosted-deployment-failure.jpg'); } catch {} }
}).finally(async () => {
  await browser?.close(); report.finished_at = new Date().toISOString(); await fs.mkdir(path.join(ROOT, 'reports'), { recursive: true });
  await fs.writeFile(path.join(ROOT, 'reports/hosted-deployment.json'), `${JSON.stringify(report, null, 2)}\n`);
});
