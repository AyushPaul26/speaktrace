const test = require('node:test');
const assert = require('node:assert/strict');
const { valuesAtWords } = require('./diagnostics.js');
test('word contours use actual frame times and robust medians', () => {
  assert.deepEqual(valuesAtWords({words: [{start: 1, end: 2, score: .9}, {start: 3, end: 4, score: .9}], features: {times: [0, 1, 1.5, 2, 3, 3.5, 4], rms_db: [100, -6, -5, 20, 1, 2, 3]}}, 'rms_db'), [-5, 2]);
});
test('unvoiced pitch and weak alignment remain missing, never fabricated zero', () => {
  assert.deepEqual(valuesAtWords({words: [{start: 0, end: 1, score: .9}, {start: 1, end: 2, score: .2}], features: {times: [.5, 1.5], pitch_st: [null, 7]}}, 'pitch_st'), [null, null]);
});
test('numeric zero is a real value and missing arrays leave gaps', () => {
  const recording = {words: [{start: 0, end: 1, score: .9}], features: {times: [.5], rms_db: [0]}};
  assert.deepEqual(valuesAtWords(recording, 'rms_db'), [0]);
  assert.deepEqual(valuesAtWords(recording, 'pitch_st'), [null]);
});
