(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.SpeakTraceCore = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';
  const dimensions = ['pacing', 'pauses', 'energy'];
  const labels = { pacing: 'Pacing', pauses: 'Pauses', energy: 'Energy' };
  const defaults = { pacing: 40, pauses: 35, energy: 25 };
  function clamp(value, min, max) { return Math.min(max, Math.max(min, Number(value) || 0)); }
  function wordCount(text) { return (text.trim().match(/[A-Za-z]+(?:['’-][A-Za-z]+)*/g) || []).length; }
  function validateTranscript(text) {
    if (!text.trim()) return 'Enter the words spoken in both recordings.';
    if (text.length > 1600) return 'Keep the transcript within 1,600 characters.';
    if (/\d/.test(text)) return 'Write numbers as spoken words, for example “twenty three”.';
    if (/[^A-Za-z\s.,!?;:'’"“”()\-—–]/.test(text)) return 'Use an English transcript with letters and ordinary punctuation only.';
    if (wordCount(text) > 150) return 'Shorten the transcript to 150 words or fewer.';
    if (wordCount(text) < 1) return 'Enter at least one spoken word.';
    return '';
  }
  function validateFile(file) {
    if (!file) return 'Choose an audio recording.';
    if (!/\.(wav|flac|ogg|mp3)$/i.test(file.name)) return 'Choose a WAV, FLAC, OGG, or MP3 audio file.';
    if (file.size === 0) return 'This file is empty. Choose a recording with audio.';
    if (file.size > 20 * 1024 * 1024) return 'This file is larger than 20 MB. Use a shorter recording.';
    return '';
  }
  function normalizedWeights(weights) {
    if (dimensions.some(key => !Number.isFinite(weights[key]) || weights[key] < 0)) return null;
    const total = dimensions.reduce((sum, key) => sum + weights[key], 0);
    if (total <= 0) return null;
    return Object.fromEntries(dimensions.map(key => [key, weights[key] / total]));
  }
  function time(value, decimals = false) {
    const seconds = Math.max(0, Number(value) || 0);
    const minutes = Math.floor(seconds / 60);
    const remainder = seconds - minutes * 60;
    return `${minutes}:${decimals ? remainder.toFixed(1).padStart(4, '0') : Math.floor(remainder).toString().padStart(2, '0')}`;
  }
  function findWord(words, currentTime) {
    return words.findIndex(word => currentTime >= word.start && currentTime <= word.end);
  }
  function findingInterval(finding, kind, duration) {
    const start = kind === 'reference' ? finding.reference_start : finding.start;
    const end = kind === 'reference' ? finding.reference_end : finding.end;
    return { start: clamp(start, 0, duration), end: clamp(end, 0, duration) };
  }
  function playbackInterval(finding, kind, duration) {
    const interval = findingInterval(finding, kind, duration);
    return { start: clamp(interval.start - .25, 0, duration), end: clamp(interval.end + .25, 0, duration) };
  }
  function safeMediaURL(value, origin) {
    try {
      const url = new URL(value, origin);
      return url.origin === origin && url.pathname.startsWith('/media/') ? url.href : null;
    } catch { return null; }
  }
  return { dimensions, labels, defaults, clamp, wordCount, validateTranscript, validateFile, normalizedWeights, time, findWord, findingInterval, playbackInterval, safeMediaURL };
});
