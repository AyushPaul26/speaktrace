/* Local functional test. Requires an already-installed Playwright and Chrome.
 * PLAYWRIGHT_MODULE and CHROME_PATH override the optional bundled/runtime paths.
 * Uses a fresh, nonpersistent headless context: never a personal browser profile.
 */
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const os = require('node:os');
const ROOT = path.resolve(__dirname, '..');
const BASE = process.env.SPEAKTRACE_URL || 'http://127.0.0.1:8765';
const target = new URL(BASE);
assert(['127.0.0.1', 'localhost', '[::1]'].includes(target.hostname), 'Smoke tests may target loopback only');
const { valuesAtWords } = require('../web/diagnostics.js');
const { playbackInterval, time } = require('../web/core.js');
function loadPlaywright() {
  if (process.env.PLAYWRIGHT_MODULE) return require(process.env.PLAYWRIGHT_MODULE);
  try { return require('playwright'); }
  catch {
    return require(path.join(os.homedir(), '.cache', 'codex-runtimes', 'codex-primary-runtime', 'dependencies', 'node', 'node_modules', 'playwright'));
  }
}
const chrome = process.env.CHROME_PATH || path.join(process.env.ProgramFiles || 'C:/Program Files', 'Google', 'Chrome', 'Application', 'chrome.exe');
const report = {
  started_at: new Date().toISOString(), target: BASE, passed: false,
  browser: 'Headless installed Chrome; fresh nonpersistent context; no personal profile',
  controls: ['For stopped-job regression tests only, GET /api/jobs/* requests are held before forwarding, then released after editing. All POSTs create real local analyses. No analysis values, findings, or scores are stubbed.'],
  steps: [], page_errors: [], console_errors: [], artifacts: [], limitations: ['Device labels are checked against actual server and result metadata, including cache provenance. This browser check does not benchmark hardware performance.']
};
let browser, context, page;
function pass(name, evidence = {}) { report.steps.push({ name, passed: true, ...evidence }); console.log(`PASS ${name}`); }
async function waitForJob(id, timeout = 180000) {
  const stop = Date.now() + timeout;
  while (Date.now() < stop) {
    const response = await context.request.get(`${BASE}/api/jobs/${encodeURIComponent(id)}`);
    assert(response.ok(), `Job status HTTP ${response.status()}`);
    const job = await response.json();
    if (job.status === 'error') throw new Error(job.error || 'Analysis job failed');
    if (job.status === 'complete') return job.result;
    await new Promise(resolve => setTimeout(resolve, 500));
  }
  throw new Error(`Job ${id} exceeded the smoke-test timeout`);
}
async function analyzeDemo(variant = 'Generated severe pauses') {
  await page.locator('#demo-mode').click();
  await page.locator('.demo-card').filter({ hasText: 'A university welcome' }).click();
  await page.getByRole('radio', { name: variant, exact: true }).check();
  const responsePromise = page.waitForResponse(response => response.url().endsWith('/api/demos/jfk-welcome/analyze') && response.request().method() === 'POST');
  await page.locator('#analyze-button').click();
  const response = await responsePromise;
  assert.equal(response.status(), 202);
  const { job_id } = await response.json();
  await page.locator('#edit-comparison').waitFor({ state: 'visible', timeout: 180000 });
  return waitForJob(job_id);
}
async function stoppedUploadEdit(kind, reference) {
  await page.locator('#upload-mode').click();
  await page.locator('#reference-file').setInputFiles(path.join(ROOT, reference.audio));
  await page.locator('#participant-file').setInputFiles(path.join(ROOT, reference.variants.find(item => item.id === 'pauses-severe').audio));
  await page.locator('#transcript-input').fill(reference.transcript);
  let release, sawPoll;
  const held = new Promise(resolve => { release = resolve; });
  const observed = new Promise(resolve => { sawPoll = resolve; });
  const handler = async route => {
    sawPoll();
    await held;
    try { await route.continue(); } catch { /* The app is expected to abort this stale poll. */ }
  };
  await page.route('**/api/jobs/*', handler);
  try {
    const posted = page.waitForResponse(response => response.url().endsWith('/api/analyze') && response.request().method() === 'POST');
    await page.locator('#analyze-button').click();
    const response = await posted;
    assert.equal(response.status(), 202);
    const { job_id } = await response.json();
    await Promise.race([observed, new Promise((_, reject) => setTimeout(() => reject(new Error('Polling was never observed')), 15000))]);
    await page.locator('#stop-watching').click();
    assert(await page.locator('#resume-job').isVisible(), 'Stopped job should offer Resume before edits');
    const changedTranscript = `${reference.transcript} Today.`;
    if (kind === 'transcript') await page.locator('#transcript-input').fill(changedTranscript);
    else await page.locator('#participant-file').setInputFiles(path.join(ROOT, reference.audio));
    assert.equal(await page.locator('#resume-job').isVisible(), false, 'Edited inputs must invalidate old Resume');
    assert.equal(await page.locator('#analysis-notice').isVisible(), false);
    assert.equal(await page.locator('#overall-score').innerText(), '—');
    release();
    await page.unroute('**/api/jobs/*', handler);
    const oldResult = await waitForJob(job_id);
    assert.equal(oldResult.transcript, reference.transcript, 'The actual server job must retain original inputs');
    assert.equal(await page.locator('#overall-score').innerText(), '—', 'Late job completion must not populate edited inputs');
    assert.equal(await page.locator('#download-json').isEnabled(), false);
    if (kind === 'transcript') assert.equal(await page.locator('#transcript-input').inputValue(), changedTranscript);
    else assert.match(await page.locator('#participant-file-name').innerText(), /jfk-welcome\.wav/);
    pass(`Stop watching then edit ${kind} invalidates the old job`, { real_job_id: job_id, polling_control: 'GET held, then aborted/released; real POST and completed server result' });
  } finally { release(); await page.unroute('**/api/jobs/*', handler); }
}
async function main() {
  await fs.mkdir(path.join(ROOT, 'reports'), { recursive: true });
  const { chromium } = loadPlaywright();
  browser = await chromium.launch({ headless: true, executablePath: chrome, args: ['--no-first-run', '--disable-background-networking'] });
  context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, reducedMotion: 'reduce', acceptDownloads: true });
  page = await context.newPage();
  page.setDefaultTimeout(15000);
  page.on('pageerror', error => report.page_errors.push(error.message));
  page.on('console', message => { if (message.type() === 'error') report.console_errors.push(message.text()); });
  const healthResponse = await context.request.get(`${BASE}/api/health`);
  assert(healthResponse.ok()); report.health = await healthResponse.json();
  assert(report.health.model_ready, 'The model must be installed before this smoke test');
  await page.goto(BASE, { waitUntil: 'networkidle' });
  await page.locator('.demo-card').first().waitFor();
  assert.equal(await page.locator('#overall-score').innerText(), '—');
  assert.equal(await page.locator('[data-diagnostic="rms_db"]').isEnabled(), false);
  pass('Initial no-result state and disabled diagnostics');

  const result = await analyzeDemo();
  report.pause_result = { id: result.id, rubric: result.rubric.version, score: result.summary.score, compute: result.compute, findings: result.findings.map(item => ({ type: item.type, start: item.start, end: item.end, evidence: item.evidence })) };
  const pause = result.findings.find(item => item.type === 'pauses');
  assert(pause, 'Real severe-pause demo must contain a measured pause finding');
  const excess = pause.evidence.participant - pause.evidence.reference;
  assert(excess > 1.5 && excess < 2.2, `Expected roughly 1.8 s excess pause; got ${excess}`);
  assert.notEqual(result.summary.score, null);
  pass('Real severe-pause demo displays a measured excess pause', { excess_seconds: excess, score: result.summary.score, rubric: result.rubric.version });

  await page.locator(`[data-finding="${pause.id}"]`).click();
  for (const kind of ['reference', 'participant']) {
    const interval = playbackInterval(pause, kind, result[kind].duration);
    const replay = page.getByRole('button', { name: new RegExp(`^Play ${kind} context`) });
    assert((await replay.innerText()).includes(`${time(interval.start, true)}–${time(interval.end, true)}`));
    await replay.click();
    await page.waitForFunction(({ kind, start }) => {
      const audio = document.querySelector(`#${kind}-track audio`);
      return !audio.paused && audio.currentTime >= start;
    }, { kind, start: interval.start });
    await page.waitForFunction(({ kind, end }) => {
      const audio = document.querySelector(`#${kind}-track audio`);
      return audio.paused && audio.currentTime >= end - .06 && audio.currentTime <= end + .4;
    }, { kind, end: interval.end });
    pass(`${kind} evidence context plays and stops at its padded endpoint`, interval);
  }

  const features = [['rms_db', 'Energy', 'dB'], ['pitch_st', 'Pitch', 'st'], ['spectral_centroid', 'Spectrum', 'Hz']];
  for (const [feature, label, unit] of features) {
    await page.getByRole('button', { name: label, exact: true }).click();
    assert.equal(await page.locator(`[data-diagnostic="${feature}"]`).getAttribute('aria-pressed'), 'true');
    assert.equal(await page.locator('#diagnostic-chart .diagnostic-line').count(), 2);
    assert.equal(await page.locator('#diagnostic-table tr').count(), result.participant.words.length);
    const values = valuesAtWords(result.participant, feature);
    const index = values.findIndex(Number.isFinite);
    assert(index >= 0, `Expected measured ${feature} values`);
    assert.equal(await page.locator('#diagnostic-table tr').nth(index).locator('td').nth(2).textContent(), `${values[index].toFixed(1)} ${unit}`);
    assert.match(await page.locator('#diagnostic-description').innerText(), /transcript word, not elapsed seconds/);
    pass(`${label} toggle renders real contours and exact word values`, { rows: values.length, measured_words: values.filter(Number.isFinite).length });
  }
  await page.locator('#diagnostic-values summary').click();
  const index = Math.min(25, result.participant.words.length - 1);
  await page.locator('#diagnostic-table tr').nth(index).getByRole('button').click();
  const expected = { reference: result.reference.words[index].start, participant: result.participant.words[index].start };
  await page.waitForFunction(expectedTimes => Math.abs(document.querySelector('#reference-track audio').currentTime - expectedTimes.reference) < .06 && Math.abs(document.querySelector('#participant-track audio').currentTime - expectedTimes.participant) < .06, expected);
  assert.equal(await page.evaluate(() => document.activeElement.id), `word-${index}`);
  pass('Diagnostic table seeks each recording to its own word timestamp', expected);

  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole('button', { name: 'Pitch', exact: true }).click();
  assert.equal(await page.locator('[data-diagnostic="pitch_st"]').getAttribute('aria-pressed'), 'true');
  await page.locator('#diagnostic-table tr').nth(5).getByRole('button').click();
  assert.equal(await page.evaluate(() => document.activeElement.id), 'word-5');
  await page.locator(`[data-finding="${pause.id}"]`).click();
  const narrow = await page.evaluate(() => ({ width: innerWidth, scrollWidth: document.documentElement.scrollWidth, captionWidth: document.querySelector('#summary-caption').getBoundingClientRect().width }));
  assert(narrow.scrollWidth <= narrow.width, `Narrow viewport overflow: ${JSON.stringify(narrow)}`);
  await page.screenshot({ path: path.join(ROOT, 'reports/studio-final-narrow.jpg'), fullPage: true, type: 'jpeg', quality: 85 });
  report.artifacts.push('reports/studio-final-narrow.jpg'); pass('390 px responsive diagnostics, table seek and wrapping', narrow);
  await page.setViewportSize({ width: 1440, height: 1000 });
  const manifest = JSON.parse(await fs.readFile(path.join(ROOT, 'data/manifest.json'), 'utf8'));
  const reference = manifest.references.find(item => item.id === 'jfk-welcome');
  await stoppedUploadEdit('transcript', reference);
  await stoppedUploadEdit('file', reference);
  const finalResult = await analyzeDemo();
  await page.getByRole('button', { name: 'Energy', exact: true }).click();
  const chosen = page.locator('.finding').filter({ hasText: /pause/i }).first();
  await chosen.click();
  await page.locator('#diagnostic-values').evaluate(element => { element.open = false; });
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: path.join(ROOT, 'reports/studio-final.jpg'), fullPage: true, type: 'jpeg', quality: 90 });
  report.artifacts.push('reports/studio-final.jpg');
  const deviceText = await page.locator('#connection-status').innerText();
  assert(deviceText.includes(report.health.device === 'cuda' ? 'GPU' : 'CPU'));
  const resultText = await page.locator('#result-meta').innerText();
  const resultDevice = finalResult.compute.device === 'cuda' ? 'GPU' : finalResult.compute.device === 'cuda+cpu' ? 'GPU + CPU' : 'CPU';
  assert(resultText.includes(`${resultDevice} alignment`));
  assert.equal(resultText.includes('includes cached alignment'), Boolean(finalResult.compute.cached_alignment));
  pass('Displayed devices and cache disclosure agree with actual runtime/result metadata', { text: deviceText, device: report.health.device, result_text: resultText, result_compute: finalResult.compute });
  assert.equal(report.page_errors.length, 0, 'No uncaught browser page errors');
  assert.equal(report.console_errors.length, 0, 'No browser console errors');
  pass('No page or console errors');
  report.passed = true;
}
main().catch(async error => {
  report.error = error.stack || String(error);
  console.error(report.error);
  if (page) {
    try { await page.screenshot({ path: path.join(ROOT, 'reports/browser-smoke-failure.jpg'), fullPage: true }); report.artifacts.push('reports/browser-smoke-failure.jpg'); } catch { /* Preserve the primary failure. */ }
  }
  process.exitCode = 1;
}).finally(async () => {
  report.finished_at = new Date().toISOString();
  await fs.writeFile(path.join(ROOT, 'reports/browser-smoke.json'), `${JSON.stringify(report, null, 2)}\n`);
  if (browser) await browser.close();
});
