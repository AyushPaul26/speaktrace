const test = require('node:test');
const assert = require('node:assert/strict');
const C = require('./core.js');

test('audio validation rejects empty, oversized and unsupported files', () => {
  assert.match(C.validateFile(null), /Choose/);
  assert.match(C.validateFile({ name: 'sample.wav', size: 0 }), /empty/);
  assert.match(C.validateFile({ name: 'sample.exe', size: 100 }), /WAV/);
  assert.match(C.validateFile({ name: 'sample.wav', size: 20 * 1024 * 1024 + 1 }), /20 MB/);
  assert.equal(C.validateFile({ name: 'SAMPLE.WAV', size: 1024 }), '');
});
test('transcript validation catches limits, numerals and unsupported text', () => {
  assert.match(C.validateTranscript('  '), /Enter/);
  assert.match(C.validateTranscript('There are 12 words.'), /numbers/);
  assert.match(C.validateTranscript('A good idea 😊'), /English/);
  assert.match(C.validateTranscript('word '.repeat(151)), /150 words/);
  assert.equal(C.validateTranscript('We’re ready. Twenty three people came.'), '');
});
test('weights normalize and reject meaningless totals', () => {
  assert.deepEqual(C.normalizedWeights({ pacing: 40, pauses: 35, energy: 25 }), { pacing: .4, pauses: .35, energy: .25 });
  assert.equal(C.normalizedWeights({ pacing: 0, pauses: 0, energy: 0 }), null);
  assert.equal(C.normalizedWeights({ pacing: -1, pauses: 35, energy: 25 }), null);
  assert.equal(C.normalizedWeights({ pacing: NaN, pauses: 35, energy: 25 }), null);
  assert.deepEqual(C.normalizedWeights({ pacing: 50, pauses: 0, energy: 0 }), { pacing: 1, pauses: 0, energy: 0 });
});
test('evidence intervals use each recording’s own coordinates', () => {
  const finding = { start: 7, end: 12, reference_start: 4, reference_end: 8 };
  assert.deepEqual(C.findingInterval(finding, 'reference', 10), { start: 4, end: 8 });
  assert.deepEqual(C.findingInterval(finding, 'participant', 11), { start: 7, end: 11 });
});
test('evidence replay adds audible context without changing measured intervals', () => {
  const finding = { start: 8.1, end: 9.9, reference_start: 8, reference_end: 8 };
  assert.deepEqual(C.playbackInterval(finding, 'reference', 22), { start: 7.75, end: 8.25 });
  assert.deepEqual(C.playbackInterval(finding, 'participant', 24), { start: 7.85, end: 10.15 });
  assert.deepEqual(C.findingInterval(finding, 'reference', 22), { start: 8, end: 8 });
  assert.deepEqual(finding, { start: 8.1, end: 9.9, reference_start: 8, reference_end: 8 });
});
test('evidence replay context clips to the beginning and end of each recording', () => {
  const finding = { start: 9.9, end: 10, reference_start: 0, reference_end: 0 };
  assert.deepEqual(C.playbackInterval(finding, 'reference', 8), { start: 0, end: .25 });
  assert.deepEqual(C.playbackInterval(finding, 'participant', 10), { start: 9.65, end: 10 });
  assert.deepEqual(C.playbackInterval(finding, 'reference', .1), { start: 0, end: .1 });
});
test('playback word detection does not highlight words during silence', () => {
  const words = [{ start: 1, end: 2 }, { start: 3, end: 4 }];
  assert.equal(C.findWord(words, 1.5), 0);
  assert.equal(C.findWord(words, 2.5), -1);
  assert.equal(C.findWord(words, 3.5), 1);
});
test('media URLs cannot send recordings to external or executable URLs', () => {
  const origin = 'http://127.0.0.1:8765';
  assert.equal(C.safeMediaURL('/media/results/a.wav', origin), `${origin}/media/results/a.wav`);
  assert.equal(C.safeMediaURL('https://example.org/media/a.wav', origin), null);
  assert.equal(C.safeMediaURL('javascript:alert(1)', origin), null);
  assert.equal(C.safeMediaURL('/api/health', origin), null);
  assert.equal(C.safeMediaURL('/media/../api/health', origin), null);
});
test('elapsed time formatting preserves audio precision', () => {
  assert.equal(C.time(65.2), '1:05');
  assert.equal(C.time(5.2, true), '0:05.2');
  assert.equal(C.time(-3), '0:00');
});
