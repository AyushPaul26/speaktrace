const test = require('node:test');
const assert = require('node:assert/strict');
const H = require('./hosted.js');
const signal = (seconds = 2, peak = .25) => Float32Array.from({ length: seconds * 16000 }, (_, i) => Math.sin(2 * Math.PI * 220 * i / 16000) * peak);

test('canonical WAV has PCM16 mono 16k header and exact sample count', () => {
  const input = signal(), result = H.canonicalWav(input), wav = new DataView(result.bytes);
  assert.equal(result.bytes.byteLength, 64044);
  assert.equal(wav.getUint16(20, true), 1);
  assert.equal(wav.getUint16(22, true), 1);
  assert.equal(wav.getUint32(24, true), 16000);
  assert.equal(wav.getUint16(34, true), 16);
  assert.equal(wav.getUint32(40, true), input.length * 2);
  assert.equal(result.gain, 1);
  for (const i of [3, 400, 12345]) assert.equal(wav.getInt16(44 + i * 2, true), Math.floor(input[i] * 32768));
});

test('quiet and overrange floating samples receive uniform gain before PCM quantization', () => {
  for (const peak of [.0001, 2, .01]) {
    const input = signal(2, peak), result = H.canonicalWav(input), wav = new DataView(result.bytes);
    let maximum = 0;
    for (let i = 0; i < input.length; i++) maximum = Math.max(maximum, Math.abs(wav.getInt16(44 + i * 2, true) / 32768));
    assert.ok(maximum >= .01 && maximum <= 1);
    if (peak !== .01) assert.ok(Math.abs(maximum - .95) < 1 / 32768);
  }
});

test('duration, silence, invalid samples and invalid amplitude reject before upload', () => {
  for (const input of [signal(1), signal(61), new Float32Array(32000), signal(2, 5)]) assert.throws(() => H.canonicalWav(input));
  const invalid = signal(); invalid[42] = NaN;
  assert.throws(() => H.canonicalWav(invalid));
  assert.throws(() => H.canonicalWav(signal(), 48000));
});

test('hosted duration cap accepts 30 seconds and rejects longer clips', () => {
  H.validateDuration(2); H.validateDuration(30); H.validateDuration(60, 60);
  for (const duration of [1.99, 30.0001, 31, 60, NaN]) assert.throws(() => H.validateDuration(duration), /2 and 30 seconds/);
  assert.throws(() => H.validateDuration(21, 20), /2 and 20 seconds/);
});

test('two maximum hosted-duration WAVs plus real multipart encoding fit request limit', async () => {
  const body = new FormData(), wav = H.canonicalWav(signal(30));
  body.append('reference', new Blob([wav.bytes]), 'reference.wav');
  body.append('participant', new Blob([wav.bytes]), 'participant.wav');
  body.append('transcript', 'a'.repeat(1600)); body.append('weights', JSON.stringify({ pacing: 40, pauses: 35, energy: 25 }));
  const payload = await new Response(body).blob();
  assert.ok(payload.size < H.MAX_BODY_BYTES);
  assert.ok(payload.size > 1920000);
});

test('media only accepts exact same-origin demo paths and explicitly minted blobs', () => {
  const origin = 'https://speaktrace.example', trusted = new Set(['blob:https://speaktrace.example/ours']);
  assert.equal(H.safeMediaURL('/data/references/jfk-welcome.wav', origin), `${origin}/data/references/jfk-welcome.wav`);
  assert.equal(H.safeMediaURL('/data/variants/jfk-welcome/pauses-severe.wav', origin), `${origin}/data/variants/jfk-welcome/pauses-severe.wav`);
  assert.equal(H.safeMediaURL([...trusted][0], origin, trusted), [...trusted][0]);
  for (const value of ['blob:https://speaktrace.example/untrusted', '//evil.example/data/references/a.wav', '/data/secret.json', '/data/references/../secrets.wav', '/data/references/a.wav?redirect=evil', 'javascript:alert(1)', null]) assert.equal(H.safeMediaURL(value, origin, trusted), null);
});

test('JSON export removes transient blob handles without mutating displayed result', () => {
  const result = { reference: { url: 'blob:ours' }, participant: { url: '/data/references/a.wav' }, transcript: 'hello' };
  const exported = H.exportableResult(result);
  assert.equal(exported.reference.url, null);
  assert.equal(result.reference.url, 'blob:ours');
  assert.equal(exported.participant.url, result.participant.url);
});

test('printable report escapes every user value and carries evidence, provenance and rubric', () => {
  const attack = '<script>alert("injected")</script>';
  const result = { title: attack, transcript: attack, summary: { score: 80, caption: attack, dimensions: [{ label: attack, score: 80, weight: .35 }] }, findings: [{ title: attack, explanation: attack, advice: attack, evidence: { unit: attack, measurement: attack }, start: 1, end: 2 }], warnings: [attack], provenance: { source: attack }, rubric: { version: 'reference-relative-1.1.0' }, compute: { model: attack }, audio_processing: { gain: 1 } };
  const html = H.printableReport(result);
  assert.ok(!html.includes('<script>'));
  assert.ok(html.includes('&lt;script&gt;'));
  assert.ok(html.includes('reference-relative-1.1.0'));
  assert.ok(html.includes('Participant 1.00–2.00s'));
  assert.ok(html.includes('Content-Security-Policy'));
  assert.ok(html.includes('Audio is not embedded'));
});
