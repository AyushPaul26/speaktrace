/* Word-indexed acoustic contours. No resampling of one speaker's time axis. */
(function () {
  'use strict';
  function valuesAtWords(recording, feature) {
    const times = recording.features?.times || [], values = recording.features?.[feature] || [];
    return (recording.words || []).map(word => {
      if (word.score < 0.35) return null;
      const window = times.flatMap((t, index) => t >= word.start && t <= word.end && Number.isFinite(values[index]) ? [values[index]] : []);
      if (!window.length) return null;
      window.sort((a, b) => a - b);
      const mid = Math.floor(window.length / 2);
      return window.length % 2 ? window[mid] : (window[mid - 1] + window[mid]) / 2;
    });
  }
  if (typeof module === 'object' && module.exports) module.exports = { valuesAtWords };
  if (typeof document === 'undefined') return;
  const $ = id => document.getElementById(id);
  const options = {
    rms_db: ['dB', 'Relative energy, median within each word. Each recording uses its own voiced-energy baseline.'],
    pitch_st: ['st', 'Pitch in semitones relative to each recording’s voiced median. Unvoiced words leave gaps.'],
    spectral_centroid: ['Hz', 'FFT spectral centroid, median within each word. Spectral brightness is a diagnostic, not a vocal-clarity score.']
  };
  let result = null, feature = 'rms_db';
  function node(tag, text, className) { const value = document.createElement(tag); if (text !== undefined) value.textContent = text; if (className) value.className = className; return value; }
  function svg(tag, attributes, text) { const value = document.createElementNS('http://www.w3.org/2000/svg', tag); Object.entries(attributes).forEach(([key, item]) => value.setAttribute(key, item)); if (text !== undefined) value.textContent = text; return value; }
  function seek(index) { const word = $(`word-${index}`); if (word) { word.click(); word.focus({ preventScroll: true }); } }
  function render() {
    const host = $('diagnostic-chart'), body = $('diagnostic-table');
    host.replaceChildren(); body.replaceChildren(); $('diagnostic-values').hidden = !result;
    document.querySelectorAll('[data-diagnostic]').forEach(button => { button.disabled = !result; button.setAttribute('aria-pressed', String(button.dataset.diagnostic === feature)); });
    if (!result) { $('diagnostic-description').textContent = 'Analyze audio to compare measured acoustic features at corresponding transcript words.'; return; }
    const unit = options[feature][0], ref = valuesAtWords(result.reference, feature), part = valuesAtWords(result.participant, feature);
    $('diagnostic-description').textContent = `${options[feature][1]} Aligned by transcript word, not elapsed seconds. Weakly aligned words are omitted. Select a point or table word to seek both recordings.`;
    const finite = [...ref, ...part].filter(Number.isFinite), min = finite.length ? Math.floor(Math.min(...finite)) : -1, max = finite.length ? Math.ceil(Math.max(...finite)) : 1;
    const range = Math.max(max - min, 1), lower = min - range * .1, upper = max + range * .1;
    const count = Math.max(ref.length, part.length), x = index => 50 + index / Math.max(1, count - 1) * 580, y = value => 160 - (value - lower) / (upper - lower) * 140;
    const chart = svg('svg', { viewBox: '0 0 660 200', role: 'img', 'aria-label': `${feature === 'rms_db' ? 'Energy' : feature === 'pitch_st' ? 'Pitch' : 'Spectral centroid'} by transcript word. Reference is solid teal; participant is dashed navy. The table provides exact values.` });
    for (let i = 0; i < 3; i++) {
      const value = lower + (upper - lower) * i / 2, height = y(value);
      chart.append(svg('line', { x1: 50, x2: 630, y1: height, y2: height, class: 'diagnostic-grid' }));
      chart.append(svg('text', { x: 44, y: height + 4, 'text-anchor': 'end', class: 'diagnostic-label' }, String(Math.round(value))));
    }
    chart.append(svg('text', { x: 50, y: 12, class: 'diagnostic-label' }, unit));
    [1, Math.ceil(count / 2), count].forEach(number => chart.append(svg('text', { x: x(number - 1), y: 185, 'text-anchor': 'middle', class: 'diagnostic-label' }, `Word ${number}`)));
    [[ref, 'reference'], [part, 'participant']].forEach(([values, kind]) => {
      let path = '', connected = false;
      values.forEach((value, index) => { if (!Number.isFinite(value)) { connected = false; return; } path += `${connected ? 'L' : 'M'}${x(index)},${y(value)} `; connected = true; });
      chart.append(svg('path', { d: path, class: `diagnostic-line ${kind}` }));
      values.forEach((value, index) => {
        if (!Number.isFinite(value)) return;
        const point = svg('circle', { cx: x(index), cy: y(value), r: 4, class: `diagnostic-point ${kind}`, 'data-word': index });
        point.append(svg('title', {}, `${kind}: ${result.participant.words[index].word}, ${value.toFixed(1)} ${unit}`));
        point.addEventListener('click', () => seek(index)); chart.append(point);
      });
    });
    host.append(chart);
    const legend = node('p', undefined, 'small diagnostic-legend');
    legend.append(node('span', '━━ Reference', 'diagnostic-reference'), node('span', '┄┄ Participant', 'diagnostic-participant')); host.append(legend);
    result.participant.words.forEach((word, index) => {
      const row = node('tr'), name = node('td'), button = node('button', `${index + 1}. ${word.word}`, 'text-button'); button.type = 'button'; button.addEventListener('click', () => seek(index)); name.append(button);
      row.append(name, node('td', Number.isFinite(ref[index]) ? `${ref[index].toFixed(1)} ${unit}` : 'Not assessed'), node('td', Number.isFinite(part[index]) ? `${part[index].toFixed(1)} ${unit}` : 'Not assessed')); body.append(row);
    });
  }
  document.querySelectorAll('[data-diagnostic]').forEach(button => button.addEventListener('click', () => { feature = button.dataset.diagnostic; render(); }));
  window.addEventListener('speaktrace:result', event => { result = event.detail; render(); });
})();
