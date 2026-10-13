/* Frontend contract test with explicit fixture API responses. It does not
 * measure model quality or prove a cloud deployment; deployment QA is separate.
 * Uses installed Chrome + Playwright, a fresh context, and no user profile. */
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const os = require('node:os');
const http = require('node:http');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || path.join(os.homedir(), '.cache', 'codex-runtimes', 'codex-primary-runtime', 'dependencies', 'node', 'node_modules', 'playwright'));

function stereoFloatWav(seconds) {
  const samples = seconds * 48000, data = Buffer.alloc(44 + samples * 8);
  data.write('RIFF', 0); data.writeUInt32LE(data.length - 8, 4); data.write('WAVEfmt ', 8);
  data.writeUInt32LE(16, 16); data.writeUInt16LE(3, 20); data.writeUInt16LE(2, 22);
  data.writeUInt32LE(48000, 24); data.writeUInt32LE(384000, 28); data.writeUInt16LE(8, 32); data.writeUInt16LE(32, 34); data.write('data', 36); data.writeUInt32LE(samples * 8, 40);
  for (let i = 0; i < samples; i++) {
    data.writeFloatLE(.5 * Math.sin(2 * Math.PI * 220 * i / 48000), 44 + i * 8);
    data.writeFloatLE(.25 * Math.sin(2 * Math.PI * 220 * i / 48000), 48 + i * 8);
  }
  return data;
}

(async () => {
  const fixtureResult = {
    id: 'fixture-result', mode: 'upload', title: 'Frontend contract fixture', created_at: '2026-10-13T00:00:00Z', transcript: 'Hello world',
    reference: { name: 'reference.wav', duration: 3, url: null, words: [{ word: 'Hello', start: .2, end: 1, quality: .9 }, { word: 'world', start: 1.2, end: 2, quality: .9 }], features: { waveform: [] } },
    participant: { name: 'participant.wav', duration: 3, url: null, words: [{ word: 'Hello', start: .2, end: 1, quality: .9 }, { word: 'world', start: 1.2, end: 2, quality: .9 }], features: { waveform: [] } },
    summary: { score: 100, status: 'complete', caption: 'Fixture comparison for frontend behavior only.', dimensions: [], assessed_word_count: 2, total_word_count: 2 },
    findings: [], warnings: [], compute: { device: 'cpu', seconds: 1 }, rubric: { version: 'fixture' }, provenance: {},
  };
  let received, releaseAnalysis, analysisObserved;
  const observed = new Promise(resolve => { analysisObserved = resolve; });
  const gate = new Promise(resolve => { releaseAnalysis = resolve; });
  const server = http.createServer(async (req, res) => {
    try {
      const json = data => { res.setHeader('Content-Type', 'application/json'); res.end(JSON.stringify(data)); };
      if (req.url === '/api/health') return json({ deployment: 'vercel', synchronous: true, model_ready: true, device: 'cpu', upload_max_bytes: 4200000 });
      if (req.url === '/api/demos') return json({ demos: [] });
      if (req.url === '/api/hosted/analyze') {
        const chunks = []; for await (const chunk of req) chunks.push(chunk);
        received = new Request('http://localhost/api/hosted/analyze', { method: 'POST', headers: req.headers, body: Buffer.concat(chunks), duplex: 'half' });
        analysisObserved(); await gate; return json(fixtureResult);
      }
      const allowed = req.url === '/' ? 'index.html' : /^\/web\/[a-z.]+$/.test(req.url) ? req.url.slice(5) : null;
      if (!allowed) { res.statusCode = 404; res.end(); return; }
      res.setHeader('Content-Type', allowed.endsWith('.js') ? 'text/javascript' : allowed.endsWith('.css') ? 'text/css' : 'text/html');
      res.end(await fs.readFile(path.join(__dirname, allowed)));
    } catch (error) { res.statusCode = 500; res.end(String(error)); }
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  let browser;
  try {
    browser = await chromium.launch({ headless: true, executablePath: process.env.CHROME_PATH || path.join(process.env.ProgramFiles || 'C:/Program Files', 'Google', 'Chrome', 'Application', 'chrome.exe') });
    const context = await browser.newContext({ acceptDownloads: true });
    const page = await context.newPage(); const errors = []; page.on('pageerror', error => errors.push(error.message));
    await page.goto(`http://127.0.0.1:${server.address().port}/`);
    await page.waitForFunction(() => document.getElementById('device-badge').textContent === 'CPU · CLOUD');
    assert.equal(await page.locator('#privacy-heading').innerText(), 'Cloud processing, explained.');
    await page.locator('#upload-mode').click();
    assert.equal(await page.locator('#privacy-notice').isVisible(), true);
    const file = { name: 'stereo.wav', mimeType: 'audio/wav', buffer: stereoFloatWav(3) };
    await page.locator('#reference-file').setInputFiles(file); await page.locator('#participant-file').setInputFiles(file);
    await page.locator('#transcript-input').fill('Hello world');
    await page.locator('#analyze-button').click(); await observed;
    assert.equal(await page.locator('#job-progress').getAttribute('value'), null);
    assert.match(await page.locator('#job-stage').innerText(), /cloud CPU/);
    const body = await received.formData();
    assert.equal(body.get('transcript'), 'Hello world');
    const uploaded = Buffer.from(await body.get('reference').arrayBuffer());
    assert.equal(uploaded.readUInt16LE(20), 1); assert.equal(uploaded.readUInt16LE(22), 1);
    assert.equal(uploaded.readUInt32LE(24), 16000); assert.equal(uploaded.readUInt16LE(34), 16);
    assert.equal(uploaded.length, 96044);
    releaseAnalysis();
    await page.locator('#edit-comparison').waitFor({ state: 'visible' });
    const playback = await page.locator('#reference-track audio').evaluate(async audio => Array.from(new Uint8Array(await (await fetch(audio.src)).arrayBuffer())));
    assert.deepEqual(Buffer.from(playback), uploaded, 'Playback is byte-for-byte the canonical upload');
    const downloading = page.waitForEvent('download'); await page.locator('#download-json').click(); const download = await downloading;
    const stream = await download.createReadStream(); const chunks = []; for await (const chunk of stream) chunks.push(chunk);
    const exported = JSON.parse(Buffer.concat(chunks).toString());
    assert.equal(exported.reference.url, null); assert.equal(exported.audio_processing.browser_preparation.reference.original_channels, 2);
    const popupPromise = page.waitForEvent('popup'); await page.locator('#print-report').click(); const popup = await popupPromise;
    await popup.waitForLoadState(); assert.match(await popup.locator('body').innerText(), /Frontend contract fixture/);
    assert.match(await popup.locator('body').innerText(), /Hosted speech comparison/); await popup.close();
    const oldURL = await page.locator('#reference-track audio').getAttribute('src');
    await page.locator('#edit-comparison').click(); await page.locator('#transcript-input').fill('Hello again');
    assert.equal(await page.locator('#download-json').isDisabled(), true);
    assert.equal(await page.evaluate(async url => { try { await fetch(url); return false; } catch { return true; } }, oldURL), true, 'Changing inputs revokes playback URLs');
    assert.deepEqual(errors, []);
    console.log('PASS hosted frontend contract: real Web Audio 48k stereo → 16k mono, PCM identity, multipart upload, privacy, indeterminate progress, JSON and HTML exports, invalidation; fixture API only.');
  } finally { releaseAnalysis(); await browser?.close(); await new Promise(resolve => server.close(resolve)); }
})().catch(error => { console.error(error); process.exitCode = 1; });
