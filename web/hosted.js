(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.SpeakTraceHosted = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';
  const SAMPLE_RATE = 16000;
  const MAX_BODY_BYTES = 4200000;

  // PCM16 is the upload and playback representation. The server validates it
  // again; browser checks are for understandable errors and request-size limits.
  function canonicalWav(samples, sampleRate = SAMPLE_RATE) {
    if (sampleRate !== SAMPLE_RATE) throw new Error('Audio must be resampled to 16 kHz before upload.');
    if (samples.length / sampleRate < 2 || samples.length / sampleRate > 60) throw new Error('Choose a recording between 2 and 60 seconds long.');
    let peak = 0, sum = 0, squareSum = 0;
    for (const sample of samples) {
      if (!Number.isFinite(sample)) throw new Error('Audio contains invalid sample values. Export a standard WAV file.');
      peak = Math.max(peak, Math.abs(sample)); sum += sample; squareSum += sample * sample;
    }
    if (peak > 4) throw new Error('Audio sample levels are invalid. Export a standard PCM WAV file.');
    if (Math.sqrt(Math.max(0, squareSum / samples.length - (sum / samples.length) ** 2)) < 1e-5) throw new Error('This recording is silent or too quiet. Record audible speech and try again.');
    let gain = peak > 1 || peak < .01 ? .95 / peak : 1;
    const pcm = new Int16Array(samples.length);
    function quantize() {
      let pcmPeak = 0;
      for (let i = 0; i < samples.length; i++) {
        const value = Math.fround(samples[i] * gain);
        pcm[i] = Math.max(-32768, Math.min(32767, Math.floor(value * 32768)));
        pcmPeak = Math.max(pcmPeak, Math.abs(pcm[i]) / 32768);
      }
      return pcmPeak;
    }
    // Avoid a second server gain change at the .01 quantization boundary.
    if (quantize() < .01) { gain = .95 / peak; quantize(); }
    const bytes = new ArrayBuffer(44 + pcm.length * 2), view = new DataView(bytes);
    const ascii = (offset, value) => { for (let i = 0; i < value.length; i++) view.setUint8(offset + i, value.charCodeAt(i)); };
    ascii(0, 'RIFF'); view.setUint32(4, bytes.byteLength - 8, true); ascii(8, 'WAVE'); ascii(12, 'fmt ');
    view.setUint32(16, 16, true); view.setUint16(20, 1, true); view.setUint16(22, 1, true);
    view.setUint32(24, sampleRate, true); view.setUint32(28, sampleRate * 2, true); view.setUint16(32, 2, true); view.setUint16(34, 16, true);
    ascii(36, 'data'); view.setUint32(40, pcm.length * 2, true);
    for (let i = 0; i < pcm.length; i++) view.setInt16(44 + i * 2, pcm[i], true);
    return { bytes, gain, sampleRate, duration: pcm.length / sampleRate };
  }

  async function prepareAudio(file, signal) {
    if (!file || file.size > 20 * 1024 * 1024 || file.size === 0) throw new Error('Choose a nonempty recording no larger than 20 MB.');
    const checkCancelled = () => { if (signal?.aborted) throw new DOMException('Cancelled', 'AbortError'); };
    checkCancelled();
    const Context = globalThis.OfflineAudioContext || globalThis.webkitOfflineAudioContext;
    if (!Context) throw new Error('This browser cannot prepare audio. Use a current desktop browser or the local app.');
    const context = new Context(1, 1, SAMPLE_RATE);
    let decoded;
    try { decoded = await context.decodeAudioData(await file.arrayBuffer()); }
    catch { throw new Error('This browser could not decode the recording. Export it as PCM WAV and try again.'); }
    checkCancelled();
    if (![1, 2].includes(decoded.numberOfChannels)) throw new Error('Choose a mono or stereo audio recording.');
    if (decoded.duration < 2 || decoded.duration > 60) throw new Error('Choose a recording between 2 and 60 seconds long.');
    const channels = Array.from({ length: decoded.numberOfChannels }, (_, index) => decoded.getChannelData(index));
    const mono = new Float32Array(decoded.length);
    for (let i = 0; i < mono.length; i++) mono[i] = channels.length === 1 ? channels[0][i] : Math.fround(channels[0][i] + channels[1][i]) / 2;
    const canonical = canonicalWav(mono, decoded.sampleRate);
    return { blob: new Blob([canonical.bytes], { type: 'audio/wav' }), metadata: { original_name: file.name, original_bytes: file.size, decoded_sample_rate: decoded.sampleRate, original_channels: decoded.numberOfChannels, sample_rate: SAMPLE_RATE, encoding: 'WAV PCM16 mono', uniform_gain: canonical.gain, duration: canonical.duration, resampler: 'Browser Web Audio decodeAudioData' } };
  }

  function safeMediaURL(value, origin, trustedBlobURLs = new Set()) {
    if (typeof value !== 'string') return null;
    if (value.startsWith('blob:')) return trustedBlobURLs.has(value) ? value : null;
    try {
      const url = new URL(value, origin);
      const allowed = /^\/data\/(references\/[a-z0-9-]+\.wav|variants\/[a-z0-9-]+\/[a-z0-9-]+\.wav)$/.test(url.pathname);
      return url.origin === origin && ['https:', 'http:'].includes(url.protocol) && allowed && !url.search && !url.hash ? url.href : null;
    } catch { return null; }
  }

  function exportableResult(result) {
    const copy = JSON.parse(JSON.stringify(result));
    for (const kind of ['reference', 'participant']) {
      if (copy[kind] && typeof copy[kind].url === 'string' && copy[kind].url.startsWith('blob:')) copy[kind].url = null;
    }
    return copy;
  }

  function printableReport(result) {
    const esc = value => String(value ?? '').replace(/[&<>"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[char]);
    const number = value => Number.isFinite(value) ? value.toFixed(2) : '—';
    const summary = result.summary || {}, compute = result.compute || {};
    const dimensions = (summary.dimensions || []).map(item => `<tr><td>${esc(item.label)}</td><td>${Number.isFinite(item.score) ? number(item.score) : 'Withheld'}</td><td>${esc(item.weight)}</td></tr>`).join('');
    const findings = (result.findings || []).map(item => `<article><h3>${esc(item.title)}</h3><p>Participant ${number(item.start)}–${number(item.end)}s · Reference ${number(item.reference_start)}–${number(item.reference_end)}s</p><p>${esc(item.explanation)}</p><p>Reference: ${number(item.evidence?.reference)} · Participant: ${number(item.evidence?.participant)} ${esc(item.evidence?.unit)}</p><p>${esc(item.evidence?.measurement)}</p><p><strong>Practice:</strong> ${esc(item.advice)}</p><p>${esc(item.severity)} · Alignment quality ${number((item.confidence || 0) * 100)}%</p></article>`).join('');
    return `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'"><title>SpeakTrace comparison report</title><style>body{font:16px/1.6 system-ui,sans-serif;color:#172e40;max-width:900px;margin:48px auto;padding:0 28px}h1{font-size:40px}h2{margin-top:30px}.score{font-size:32px;color:#087d70}article{border-top:1px solid #d8e2e7;padding:12px 0}table{border-collapse:collapse;width:100%}th,td{text-align:left;padding:9px;border-bottom:1px solid #d8e2e7}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px}blockquote{margin:0;padding:16px;background:#f2f6f8}@media print{body{margin:12px;font-size:11pt}article{break-inside:avoid}}</style></head><body><p><strong>SpeakTrace</strong> · Hosted speech comparison</p><h1>${esc(result.title)}</h1><p>${esc(result.created_at)} · Report ${esc(result.id)}</p><p class="score">${Number.isFinite(summary.score) ? `${Math.round(summary.score)} / 100` : 'Score withheld'}</p><p>${esc(summary.caption)}</p><p>Assessed ${esc(summary.assessed_word_count)} of ${esc(summary.total_word_count)} words.</p><h2>Rubric scores</h2><table><thead><tr><th>Dimension</th><th>Score / 100</th><th>Weight</th></tr></thead><tbody>${dimensions}</tbody></table><h2>Evidence</h2>${findings || '<p>No scored deviations were found, or scoring was withheld. Check the status above.</p>'}<h2>Transcript</h2><blockquote>${esc(result.transcript)}</blockquote><h2>Limitations and provenance</h2><ul>${(result.warnings || []).map(item => `<li>${esc(item)}</li>`).join('')}</ul><p>Scores compare measured delivery against this reference and rubric; they are not universal speaking-quality ratings. Synthetic evaluation does not establish performance on independent human recordings.</p><pre>${esc(JSON.stringify(result.provenance || {}, null, 2))}</pre><h2>Processing and rubric</h2><p>Model: ${esc(compute.model)} · revision ${esc(compute.revision)}<br>Alignment device: ${esc(compute.device)} · ${esc(compute.precision)} · ${esc(compute.seconds)} seconds · Cached alignment: ${esc(compute.cached_alignment)}</p><pre>${esc(JSON.stringify(result.rubric || {}, null, 2))}</pre><pre>${esc(JSON.stringify(result.audio_processing || {}, null, 2))}</pre><p>Use your browser’s Print command to save this report as PDF. Audio is not embedded in this report.</p></body></html>`;
  }
  return { SAMPLE_RATE, MAX_BODY_BYTES, canonicalWav, prepareAudio, safeMediaURL, exportableResult, printableReport };
});
