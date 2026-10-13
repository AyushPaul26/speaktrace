/* SpeakTrace: buildless local and hosted analysis studio. */
(() => {
  'use strict';
  const C = window.SpeakTraceCore;
  const H = window.SpeakTraceHosted;
  const $ = id => document.getElementById(id);
  const NS = 'http://www.w3.org/2000/svg';
  const fmt = new Intl.NumberFormat('en-US', { maximumFractionDigits: 2 });
  const state = {
    mode: 'demo', demos: [], demo: null, variant: null, result: null, selected: null,
    weights: { ...C.defaults }, files: { reference: null, participant: null }, dirty: false,
    busy: false, generation: 0, controller: null, jobId: null, jobGeneration: 0,
    started: 0, elapsedTimer: null, players: {}, libraryController: null,
    healthController: null, methodologyController: null, modelReady: false, serverReady: false,
    hosted: false, objectURLs: new Set(), uploadMaxBytes: H.MAX_BODY_BYTES, maxSeconds: 60
  };
  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }
  function svg(tag, attrs = {}) {
    const node = document.createElementNS(NS, tag);
    Object.entries(attrs).forEach(([key, value]) => node.setAttribute(key, String(value)));
    return node;
  }
  function announce(text) { $('announcer').textContent = text; }
  function deviceLabel(device) {
    return device === 'cuda' ? 'GPU' : device === 'cuda+cpu' ? 'GPU + CPU' : 'CPU';
  }
  function bindAction(id, action) {
    const button = $(id);
    button.addEventListener('click', action);
    button.disabled = false;
  }
  function setNotice(text = '', tone = 'info', resume = false) {
    $('analysis-notice').hidden = !text;
    $('analysis-notice').dataset.tone = tone;
    $('analysis-notice-text').textContent = text;
    $('resume-job').hidden = !resume;
  }
  function errorText(error) {
    return error instanceof Error ? error.message : 'The request could not be completed. Try again.';
  }
  async function request(path, options = {}, parentSignal, timeout = 20000) {
    const controller = new AbortController();
    let timedOut = false;
    const abort = () => controller.abort();
    if (parentSignal?.aborted) throw new DOMException('Cancelled', 'AbortError');
    parentSignal?.addEventListener('abort', abort, { once: true });
    const timer = setTimeout(() => { timedOut = true; controller.abort(); }, timeout);
    try {
      const response = await fetch(path, { ...options, signal: controller.signal, credentials: 'same-origin' });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        const detail = typeof data.detail === 'string' ? data.detail : `The studio returned an error (${response.status}). Try again.`;
        const error = new Error(detail);
        error.status = response.status;
        throw error;
      }
      return data;
    } catch (error) {
      if (timedOut) throw new Error(state.hosted ? 'Cloud analysis took too long. The free service may be busy or starting up. Retry with shorter recordings, or use the local app.' : 'The local studio took too long to respond. Check that the server is still running.');
      if (error.name === 'TypeError') throw new Error(state.hosted ? 'Cannot reach the cloud studio. Check your connection and retry. The local app remains available from the project repository.' : 'Cannot reach the local studio. Check that the server is running, then try again.');
      throw error;
    } finally {
      clearTimeout(timer);
      parentSignal?.removeEventListener('abort', abort);
    }
  }
  function delay(ms, signal) {
    return new Promise((resolve, reject) => {
      if (signal.aborted) { reject(new DOMException('Cancelled', 'AbortError')); return; }
      const done = () => { signal.removeEventListener('abort', abort); resolve(); };
      const timer = setTimeout(done, ms);
      const abort = () => { clearTimeout(timer); reject(new DOMException('Cancelled', 'AbortError')); };
      signal.addEventListener('abort', abort, { once: true });
    });
  }
  function updateAnalyzeState() {
    const selectionReady = state.mode === 'upload' || Boolean(state.demo && state.variant);
    $('analyze-button').disabled = state.busy || !state.serverReady || !selectionReady || !C.normalizedWeights(state.weights);
    $('analyze-button').setAttribute('aria-busy', String(state.busy));
    C.dimensions.forEach(key => { $(`weight-${key}`).disabled = state.busy; });
    $('reset-weights').disabled = state.busy;
    ['reference', 'participant'].forEach(key => { $(`${key}-file`).disabled = state.busy; $(`${key}-remove`).disabled = state.busy; });
    $('transcript-input').disabled = state.busy;
  }
  function setBusy(busy) {
    state.busy = busy;
    clearInterval(state.elapsedTimer);
    $('job-status').hidden = !busy;
    if (busy) {
      const elapsed = () => { $('job-elapsed').textContent = `${C.time((Date.now() - state.started) / 1000)} elapsed`; };
      elapsed(); state.elapsedTimer = setInterval(elapsed, 1000);
    }
    updateAnalyzeState();
  }
  function invalidate() {
    const hadJob = state.busy;
    state.generation += 1;
    state.controller?.abort();
    state.controller = null; state.jobId = null; state.selected = null;
    setBusy(false); setNotice(); clearResult();
    if (hadJob) announce('Selection changed. Previous server work may continue; its result will not replace this selection.');
  }
  async function loadHealth() {
    state.healthController?.abort(); state.healthController = new AbortController();
    try {
      const data = await request('/api/health', {}, state.healthController.signal, 90000);
      state.modelReady = Boolean(data.model_ready); state.serverReady = true;
      state.hosted = data.deployment === 'vercel' && data.synchronous === true;
      state.uploadMaxBytes = Math.min(H.MAX_BODY_BYTES, Number(data.upload_max_bytes) || H.MAX_BODY_BYTES);
      state.maxSeconds = state.hosted ? Math.min(30, Number(data.max_seconds) || 30) : 60;
      applyDeploymentCopy();
      $('connection-status').replaceChildren(el('span', 'status-dot'), document.createTextNode(state.hosted ? `Cloud CPU · ${data.model_ready ? 'model ready' : 'model unavailable'}` : data.model_ready ? `Model ready · local ${deviceLabel(data.device)}` : 'Connected · model setup needed'));
      $('connection-status').dataset.state = 'ready';
      $('device-badge').textContent = state.hosted ? 'CPU · CLOUD' : `${deviceLabel(data.device)} · LOCAL`;
      $('device-badge').title = data.device_name || deviceLabel(data.device);
      $('compute-note').textContent = state.hosted ? 'Audio is sent to the cloud for CPU analysis.' : data.model_ready ? (data.warnings?.join(' ') || `${deviceLabel(data.device)} alignment · measured evidence.`) : 'Run setup.bat to install the free model.';
    } catch (error) {
      if (error.name === 'AbortError') return;
      state.serverReady = false;
      $('connection-status').replaceChildren(el('span', 'status-dot'), document.createTextNode('Studio unavailable'));
      $('connection-status').dataset.state = 'error';
    } finally { updateAnalyzeState(); }
  }
  function applyDeploymentCopy() {
    $('deployment-label').textContent = state.hosted ? 'CLOUD STUDIO' : 'LOCAL STUDIO';
    $('privacy-heading').textContent = state.hosted ? 'Cloud processing, explained.' : 'Your audio stays here.';
    $('privacy-summary').textContent = state.hosted ? 'Uploads are sent to this Vercel service. No account required. Use the local app to keep audio on your computer.' : 'Analysis runs on this computer. No account. No cloud inference.';
    $('privacy-button').textContent = state.hosted ? 'About cloud processing ↗' : 'About local storage ↗';
    $('privacy-notice').hidden = !state.hosted;
    $('method-alignment').textContent = state.hosted ? 'A pretrained English speech model locates words on the cloud CPU. Poor alignment can cause scoring to be withheld.' : 'A pretrained English speech model locates words in each recording locally, using your GPU when available or your CPU. Poor alignment can cause scoring to be withheld.';
    $('method-privacy-title').textContent = state.hosted ? 'How cloud uploads are handled' : 'Your recordings stay local';
    $('method-privacy-text').textContent = state.hosted ? 'Your browser converts each recording to 16 kHz mono PCM WAV before sending audio and the transcript to this Vercel service. The service analyzes on CPU and removes its temporary audio after the request; it does not create a saved job or audio database. Results and playback remain in this browser tab until you change the selection or leave. Hosting infrastructure may retain operational logs. Only upload audio you have permission to share. Use the local app for private, offline analysis.' : 'Inference does not send your audio to a service. Initial setup downloads the free model; analysis then runs locally. Local uploaded media and reports are retained for at most 24 hours, with cleanup at server startup and new job creation. Bundled demo media persists.';
    $('deployment-footer').textContent = `English · Reference-relative · ${state.hosted ? 'Cloud CPU' : 'Local compute'}`;
    $('audio-help').textContent = `WAV, FLAC, OGG, or MP3 · 2–${state.maxSeconds} seconds · up to 20 MB each.${state.hosted ? ' Converted in your browser to mono WAV before upload (under 4.2 MB combined). Use the local app for recordings up to 60 seconds.' : ' You can also drop a file onto either field.'}`;
  }
  async function loadLibrary() {
    state.libraryController?.abort(); state.libraryController = new AbortController();
    const signal = state.libraryController.signal;
    $('library-notice').textContent = 'Loading available recordings…';
    $('refresh-library').disabled = true;
    try {
      const data = await request('/api/demos', {}, signal);
      if (signal.aborted) return;
      state.demos = Array.isArray(data.demos) ? data.demos : [];
      $('demo-count').textContent = String(state.demos.length);
      $('library-notice').textContent = state.demos.length ? '' : 'No examples are installed yet. Add your recordings to begin.';
      renderLibrary();
      if (!state.demo && state.demos.length && state.mode === 'demo') selectDemo(state.demos[0].id);
    } catch (error) {
      if (error.name !== 'AbortError') $('library-notice').textContent = `${errorText(error)} Use the refresh button to retry.`;
    } finally { if (!signal.aborted) $('refresh-library').disabled = false; }
  }
  function renderLibrary() {
    $('demo-list').replaceChildren(...state.demos.map(demo => {
      const button = el('button', `demo-card${state.mode === 'demo' && state.demo?.id === demo.id ? ' selected' : ''}`);
      button.type = 'button'; button.setAttribute('aria-pressed', String(state.mode === 'demo' && state.demo?.id === demo.id));
      button.append(el('span', 'demo-speaker', demo.speaker || 'Archive recording'), el('span', 'demo-name', demo.title));
      const meta = el('span', 'demo-meta'); meta.append(el('span', '', 'PUBLIC-DOMAIN SOURCE'), el('span', 'mono', C.time(demo.duration)));
      button.append(meta); button.addEventListener('click', () => selectDemo(demo.id)); return button;
    }));
  }
  function setMode(mode) {
    if (state.mode !== mode) invalidate();
    state.mode = mode;
    $('demo-mode').classList.toggle('selected', mode === 'demo'); $('upload-mode').classList.toggle('selected', mode === 'upload');
    $('demo-mode').setAttribute('aria-pressed', String(mode === 'demo')); $('upload-mode').setAttribute('aria-pressed', String(mode === 'upload'));
    $('demo-setup').hidden = mode !== 'demo'; $('upload-form').hidden = mode !== 'upload';
    $('comparison-kind').textContent = mode === 'demo' ? 'EXAMPLE' : 'YOUR AUDIO';
    $('comparison-title').textContent = mode === 'demo' ? (state.demo?.title || 'Choose a recording to begin') : 'Bring your own perspective.';
    document.title = `${mode === 'upload' ? 'Your recordings' : (state.demo?.title || 'Analysis studio')} · SpeakTrace`;
    renderLibrary(); renderTranscript(); updateAnalyzeState();
    if (mode === 'demo' && !state.demo && state.demos.length) selectDemo(state.demos[0].id);
  }
  function selectDemo(id) {
    const demo = state.demos.find(item => item.id === id);
    if (!demo) return;
    invalidate(); state.demo = demo; state.variant = demo.variants?.[0]?.id || null; setMode('demo');
    $('demo-description').textContent = demo.description || 'Compare this archive reading with a controlled variation.';
    const source = $('source-line'); source.replaceChildren(el('span', '', demo.speaker || 'Archive source'), el('span', '', demo.license || 'See source license'));
    try {
      const url = new URL(demo.source_url);
      if (['https:', 'http:'].includes(url.protocol)) { const link = el('a', '', 'View original source ↗'); link.href = url.href; link.target = '_blank'; link.rel = 'noopener noreferrer'; source.append(link); }
    } catch { /* An omitted provenance URL is not converted into a link. */ }
    $('variant-options').replaceChildren(...(demo.variants || []).map((variant, index) => {
      const wrap = el('div', 'variant-option'); const input = el('input'); const label = el('label', '', variant.label);
      input.type = 'radio'; input.name = 'variant'; input.id = `variant-${index}`; input.value = variant.id; input.checked = variant.id === state.variant;
      label.htmlFor = input.id;
      input.addEventListener('change', () => { if (input.checked) { invalidate(); state.variant = variant.id; updateVariantNote(); updateAnalyzeState(); } });
      wrap.append(input, label); return wrap;
    }));
    updateVariantNote(); renderTranscript(); updateAnalyzeState();
  }
  function updateVariantNote() {
    const variant = state.demo?.variants?.find(item => item.id === state.variant);
    const clean = variant && ['clean', 'none', 'original', 'control'].includes(String(variant.flaw).toLowerCase());
    $('variant-note').textContent = !variant ? 'This example has no available variants.' : clean ? 'Clean control · the reference is compared with itself.' : 'Generated variation · transformation labels are excluded from inference.';
  }
  function renderWeights() {
    $('rubric-weights').replaceChildren(...C.dimensions.map(key => {
      const wrap = el('div', 'weight'); const label = el('label', '', C.labels[key]); label.htmlFor = `weight-${key}`;
      const output = el('output', '', `${state.weights[key]}`); output.id = `weight-value-${key}`; output.htmlFor = `weight-${key}`;
      const input = el('input'); input.type = 'range'; input.id = `weight-${key}`; input.min = '0'; input.max = '100'; input.step = '5'; input.value = String(state.weights[key]);
      input.setAttribute('aria-describedby', 'weight-note weight-error');
      input.addEventListener('input', () => { state.weights[key] = Number(input.value); output.textContent = input.value; updateWeightNote(); updateAnalyzeState(); });
      label.append(output); wrap.append(label, input); return wrap;
    })); updateWeightNote();
  }
  function updateWeightNote() {
    const normalized = C.normalizedWeights(state.weights);
    $('weight-error').textContent = normalized ? '' : 'Set at least one weight above zero.';
    $('weight-note').textContent = normalized ? `Next analysis: ${C.dimensions.map(key => `${Math.round(normalized[key] * 100)}% ${key}`).join(' · ')}` : 'Weights cannot all be zero.';
  }
  function setFieldError(key, message) {
    const input = $(key === 'transcript' ? 'transcript-input' : `${key}-file`);
    input.setAttribute('aria-invalid', String(Boolean(message))); $(`${key}-error`).textContent = message;
  }
  function updateDraftState() {
    state.dirty = Boolean(state.files.reference || state.files.participant || $('transcript-input').value.trim());
  }
  function setFile(key, file) {
    if (state.busy) return;
    const error = C.validateFile(file);
    state.files[key] = file; updateDraftState();
    if (!file) $(`${key}-file`).value = '';
    $(`${key}-file-name`).textContent = file ? `${file.name} · ${fmt.format(file.size / 1024 / 1024)} MB` : 'No recording selected';
    $(`${key}-remove`).hidden = !file; setFieldError(key, file ? error : '');
    if (file && error) announce(error);
    if (state.result || state.jobId) { invalidate(); renderTranscript(); }
  }
  function validateUpload() {
    const errors = ['reference', 'participant'].map(key => [key, C.validateFile(state.files[key])]);
    errors.push(['transcript', C.validateTranscript($('transcript-input').value)]);
    errors.forEach(([key, value]) => setFieldError(key, value));
    const first = errors.find(([, value]) => value);
    if (first) { $(first[0] === 'transcript' ? 'transcript-input' : `${first[0]}-file`).focus(); announce('Check the highlighted fields before analyzing.'); return false; }
    return true;
  }
  async function startAnalysis() {
    if (state.busy || !state.serverReady || !C.normalizedWeights(state.weights)) return;
    if (state.mode === 'upload' && !validateUpload()) return;
    if (state.mode === 'demo' && (!state.demo || !state.variant)) return;
    invalidate(); state.started = Date.now(); state.controller = new AbortController();
    const generation = state.generation, signal = state.controller.signal;
    setBusy(true); $('job-stage').textContent = state.hosted ? 'Preparing cloud comparison…' : state.mode === 'upload' ? 'Sending audio to your local studio…' : 'Preparing the comparison…'; $('job-progress').removeAttribute('value');
    $('job-help').textContent = state.hosted ? 'Cloud CPU processing. First use may take several minutes. Progress is unavailable until the result returns.' : 'Stage progress, not a time estimate. Audio stays local.';
    try {
      let response;
      const prepared = {};
      if (state.mode === 'demo') {
        response = await request(`/api/${state.hosted ? 'hosted/' : ''}demos/${encodeURIComponent(state.demo.id)}/analyze`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ variant_id: state.variant, weights: state.weights }) }, signal, state.hosted ? 330000 : 120000);
      } else {
        const body = new FormData();
        for (const kind of ['reference', 'participant']) {
          if (state.hosted) {
            $('job-stage').textContent = `Preparing ${kind} audio in your browser…`;
            prepared[kind] = await H.prepareAudio(state.files[kind], signal, state.maxSeconds);
            if (generation !== state.generation || signal.aborted) return;
            body.append(kind, prepared[kind].blob, `${kind}.wav`);
          } else body.append(kind, state.files[kind]);
        }
        body.append('transcript', $('transcript-input').value.trim()); body.append('weights', JSON.stringify(state.weights));
        if (state.hosted) {
          const encoded = new Response(body);
          const contentType = encoded.headers.get('content-type');
          const payload = await encoded.blob();
          if (payload.size > state.uploadMaxBytes) throw new Error('The prepared audio pair exceeds the cloud upload limit. Use shorter recordings.');
          $('job-stage').textContent = 'Uploading and analyzing on cloud CPU…';
          response = await request('/api/hosted/analyze', { method: 'POST', headers: { 'Content-Type': contentType }, body: payload }, signal, 330000);
        } else response = await request('/api/analyze', { method: 'POST', body }, signal, 120000);
      }
      if (generation !== state.generation || signal.aborted) return;
      if (state.hosted) {
        if (!response.id || !response.reference || !response.participant || !response.summary) throw new Error('The cloud studio returned an incomplete result. Retry with shorter recordings.');
        if (state.mode === 'upload') {
          for (const kind of ['reference', 'participant']) {
            const url = URL.createObjectURL(prepared[kind].blob); state.objectURLs.add(url);
            response[kind].url = url; response[kind].name = prepared[kind].metadata.original_name;
          }
          response.audio_processing = { ...response.audio_processing, browser_preparation: Object.fromEntries(['reference', 'participant'].map(kind => [kind, prepared[kind].metadata])) };
        }
        state.result = response; if (state.mode === 'upload') state.dirty = false;
        setBusy(false); renderResult(); loadHealth(); announce('Analysis complete. Waveforms, scores and evidence are ready.'); return;
      }
      if (!response.job_id) throw new Error('The studio did not return a job identifier. Retry the analysis.');
      state.jobId = response.job_id; state.jobGeneration = generation;
      await pollJob(response.job_id, generation, signal);
    } catch (error) {
      if (error.name !== 'AbortError' && generation === state.generation) { setBusy(false); setNotice(errorText(error), 'error', Boolean(state.jobId)); announce('Analysis needs attention. See the message below the analysis button.'); }
    }
  }
  async function pollJob(id, generation, signal) {
    let failures = 0; const watchStarted = Date.now();
    while (generation === state.generation && !signal.aborted) {
      if (Date.now() - watchStarted > 30 * 60 * 1000) throw new Error('This analysis is taking longer than expected. The server may still be working. Resume progress to check again.');
      let job;
      try { job = await request(`/api/jobs/${encodeURIComponent(id)}`, {}, signal); failures = 0; }
      catch (error) {
        if (error.name === 'AbortError') throw error;
        failures += 1;
        if (failures > 3 || (error.status && error.status < 500)) throw error;
        $('job-stage').textContent = `Connection interrupted. Reconnecting (${failures}/3)…`;
        await delay(failures * 1500, signal); continue;
      }
      if (generation !== state.generation || signal.aborted) return;
      $('job-stage').textContent = job.stage || (job.status === 'queued' ? 'Waiting for the analysis worker…' : 'Analyzing audio…');
      if (Number.isFinite(job.progress)) $('job-progress').value = C.clamp(job.progress <= 1 ? job.progress * 100 : job.progress, 0, 100);
      else $('job-progress').removeAttribute('value');
      if (job.status === 'complete') {
        if (!job.result) throw new Error('The studio finished without a readable result. Retry the comparison.');
        state.result = job.result; state.jobId = null; if (state.mode === 'upload') state.dirty = false; setBusy(false); renderResult(); loadHealth(); announce('Analysis complete. Waveforms, scores and evidence are ready.'); return;
      }
      if (job.status === 'error') { state.jobId = null; throw new Error(job.error || 'The audio could not be analyzed. Check the transcript and try clearer recordings.'); }
      await delay(1100, signal);
    }
  }
  async function resumeJob() {
    if (!state.jobId || state.busy || state.jobGeneration !== state.generation) return;
    state.controller?.abort(); state.controller = new AbortController(); setNotice(); setBusy(true);
    const generation = state.generation;
    try { await pollJob(state.jobId, generation, state.controller.signal); }
    catch (error) { if (error.name !== 'AbortError' && generation === state.generation) { setBusy(false); setNotice(errorText(error), 'error', Boolean(state.jobId)); } }
  }
  function clearResult() {
    state.result = null;
    $('setup-panel').classList.remove('has-result', 'editing');
    $('edit-comparison').hidden = true; $('edit-comparison').setAttribute('aria-expanded', 'false'); $('edit-comparison').textContent = 'Edit inputs'; $('completed-selection').hidden = true;
    Object.values(state.players).forEach(player => { player.audio.pause(); player.audio.removeAttribute('src'); player.audio.load(); });
    state.players = {};
    state.objectURLs.forEach(url => URL.revokeObjectURL(url)); state.objectURLs.clear();
    renderTrack('reference'); renderTrack('participant'); renderSummary(); renderFindings(); renderEvidence(); renderTranscript();
    $('audio-state').textContent = 'AWAITING ANALYSIS'; $('chart-caption').textContent = 'Run a comparison to reveal measured waveforms and word alignment.';
    $('transcript-action').textContent = 'Select a word after analysis';
    $('download-json').disabled = true; $('print-report').disabled = true;
    window.dispatchEvent(new CustomEvent('speaktrace:result', { detail: null }));
  }
  function renderResult() {
    const result = state.result;
    $('setup-panel').classList.add('has-result'); $('edit-comparison').hidden = false;
    $('completed-selection').hidden = false;
    $('completed-selection').textContent = result.mode === 'demo' ? `${result.provenance?.variant || 'Archive comparison'} · ${result.provenance?.synthetic ? 'Generated variation' : 'Clean control'}` : `${result.reference.name} → ${result.participant.name}`;
    renderTrack('reference', result.reference); renderTrack('participant', result.participant); renderSummary(); renderTranscript(); renderFindings(); renderEvidence();
    $('audio-state').textContent = result.summary?.status === 'unreliable' ? 'REVIEW ALIGNMENT' : 'AUDIO ALIGNED';
    $('transcript-action').textContent = 'Select any word to seek';
    $('chart-caption').textContent = 'Select an interval or word to seek both recordings. Play each track to hear the difference.';
    $('download-json').disabled = !result.id; $('print-report').disabled = !result.id;
    document.title = `${result.title || 'Analysis result'} · SpeakTrace`;
    if (result.findings?.length) selectFinding(result.findings[0].id, false);
    window.dispatchEvent(new CustomEvent('speaktrace:result', { detail: state.result }));
  }
  function playIcon(paused) {
    const icon = svg('svg', { viewBox: '0 0 16 16', 'aria-hidden': 'true' });
    if (paused) icon.append(svg('path', { d: 'M4 2.5 13 8l-9 5.5z' }));
    else icon.append(svg('path', { d: 'M4 3h3v10H4zm5 0h3v10H9z' }));
    return icon;
  }
  function renderTrack(kind, recording) {
    const host = $(`${kind}-track`); host.replaceChildren(); host.classList.toggle('participant', kind === 'participant');
    const title = kind === 'reference' ? 'Reference recording' : 'Participant recording';
    const heading = el('div', 'track-heading'), name = el('span', 'track-name', title), controls = el('div', 'track-controls');
    const time = el('span', 'track-time', `0:00 / ${recording ? C.time(recording.duration) : '—:—'}`);
    const play = el('button', 'play-button'); play.type = 'button'; play.setAttribute('aria-label', `Play ${title.toLowerCase()}`); play.disabled = !recording; play.append(playIcon(true));
    controls.append(time, play); heading.append(name, controls); host.append(heading);
    const wrap = el('div', 'waveform-wrap');
    const chart = svg('svg', { viewBox: '0 0 680 112', preserveAspectRatio: 'none', class: 'waveform', role: 'img', 'aria-label': recording ? `${title}: waveform over ${fmt.format(recording.duration)} seconds. Use the seek slider or transcript words to navigate.` : `${title}: waveform available after analysis.` });
    chart.dataset.ready = String(Boolean(recording));
    for (let i = 0; i <= 6; i++) {
      const x = 4 + i * 112;
      chart.append(svg('line', { x1: x, x2: x, y1: 4, y2: 86, class: 'waveform-grid' }));
      if (recording) { const label = svg('text', { x, y: 106, 'text-anchor': i === 0 ? 'start' : i === 6 ? 'end' : 'middle', class: 'waveform-label' }); label.textContent = `${fmt.format(recording.duration * i / 6)}s`; chart.append(label); }
    }
    chart.append(svg('line', { x1: 4, x2: 676, y1: 45, y2: 45, class: 'waveform-zero' }));
    const band = svg('rect', { x: 0, y: 3, width: 0, height: 84, class: 'waveform-band' }); chart.append(band);
    if (recording) {
      const points = recording.features?.waveform || [];
      const max = Math.max(.01, ...points.flatMap(point => [Math.abs(point.min), Math.abs(point.max)]));
      const stride = Math.max(1, Math.ceil(points.length / 260));
      points.forEach((point, index) => { if (index % stride !== 0) return; const x = 4 + C.clamp(point.t / recording.duration, 0, 1) * 672; chart.append(svg('line', { x1: x, x2: x, y1: 45 - (point.max / max) * 38, y2: 45 - (point.min / max) * 38, class: 'waveform-bar' })); });
    }
    const cursor = svg('line', { x1: 4, x2: 4, y1: 2, y2: 88, class: 'waveform-cursor', visibility: recording ? 'visible' : 'hidden' }); chart.append(cursor); wrap.append(chart);
    if (!recording) wrap.append(el('div', 'waveform-placeholder', 'Your audio, visualized after analysis.'));
    host.append(wrap);
    const seek = el('input', 'seek-control'); seek.type = 'range'; seek.min = '0'; seek.max = String(recording?.duration || 1); seek.step = '.01'; seek.value = '0'; seek.disabled = !recording; seek.setAttribute('aria-label', `Seek ${title.toLowerCase()}`); host.append(seek);
    if (!recording) return;
    const audio = document.createElement('audio'); audio.preload = 'metadata';
    const url = state.hosted ? H.safeMediaURL(recording.url, location.origin, state.objectURLs) : C.safeMediaURL(recording.url, location.origin);
    const error = el('p', 'track-error'); error.hidden = true; error.setAttribute('role', 'status'); host.append(audio, error);
    const player = { audio, recording, seek, play, cursor, band, time, stopAt: null, error }; state.players[kind] = player;
    if (url) audio.src = url; else { play.disabled = true; seek.disabled = true; error.hidden = false; error.textContent = 'This recording has no valid media URL. Analyze again to restore playback.'; }
    const showTime = () => {
      const current = audio.currentTime || 0; seek.value = String(current); seek.setAttribute('aria-valuetext', `${C.time(current, true)} of ${C.time(recording.duration, true)}`);
      time.textContent = `${C.time(current)} / ${C.time(recording.duration)}`; const x = 4 + C.clamp(current / recording.duration, 0, 1) * 672; cursor.setAttribute('x1', x); cursor.setAttribute('x2', x);
      if (!audio.paused) highlightPlaying(kind, current);
      if (player.stopAt !== null && current >= player.stopAt) { audio.pause(); player.stopAt = null; }
    };
    audio.addEventListener('timeupdate', showTime);
    audio.addEventListener('play', () => { Object.entries(state.players).forEach(([other, item]) => { if (other !== kind) item.audio.pause(); }); play.replaceChildren(playIcon(false)); play.setAttribute('aria-label', `Pause ${title.toLowerCase()}`); });
    audio.addEventListener('pause', () => { play.replaceChildren(playIcon(true)); play.setAttribute('aria-label', `Play ${title.toLowerCase()}`); });
    audio.addEventListener('ended', () => { player.stopAt = null; clearPlaying(); });
    audio.addEventListener('error', () => { error.hidden = false; error.textContent = 'Audio could not be loaded. Analyze again to restore playback.'; play.disabled = true; });
    play.addEventListener('click', () => { if (audio.paused) { player.stopAt = null; playAudio(player); } else audio.pause(); });
    seek.addEventListener('input', () => { player.stopAt = null; seekPlayer(player, Number(seek.value)); showTime(); });
    chart.addEventListener('click', event => { const rect = chart.getBoundingClientRect(); const fraction = C.clamp(((event.clientX - rect.left) / rect.width * 680 - 4) / 672, 0, 1); player.stopAt = null; seekPlayer(player, fraction * recording.duration); showTime(); });
  }
  function seekPlayer(player, time) {
    const target = C.clamp(time, 0, player.recording.duration);
    try { player.audio.currentTime = target; } catch { player.audio.addEventListener('loadedmetadata', () => { player.audio.currentTime = target; }, { once: true }); }
  }
  async function playAudio(player) {
    try { await player.audio.play(); }
    catch { player.error.hidden = false; player.error.textContent = 'Playback could not start. Try the play button again, or check that the audio file is available.'; }
  }
  function clearPlaying() { document.querySelectorAll('.word.playing').forEach(node => node.classList.remove('playing')); }
  function highlightPlaying(kind, time) {
    clearPlaying(); const index = C.findWord(state.result?.[kind]?.words || [], time); if (index >= 0) $(`word-${index}`)?.classList.add('playing');
  }
  function renderTranscript() {
    const container = $('transcript-words');
    const text = state.result?.transcript || (state.mode === 'demo' ? state.demo?.transcript : $('transcript-input').value) || '';
    if (!text) { container.replaceChildren(el('p', 'muted', 'Your transcript will appear here.')); return; }
    const words = state.result?.participant?.words;
    if (!words?.length) { container.replaceChildren(document.createTextNode(text)); return; }
    container.replaceChildren(...words.map((word, index) => {
      const button = el('button', 'word', word.word); button.type = 'button'; button.id = `word-${index}`;
      const finding = state.result.findings?.find(item => item.word_indices?.includes(index));
      if (finding) button.dataset.type = finding.type;
      button.setAttribute('aria-label', `${word.word}, participant at ${C.time(word.start, true)}${finding ? `, ${finding.title}` : ''}`);
      button.addEventListener('click', () => {
        if (finding) selectFinding(finding.id);
        else { state.selected = null; updateSelection(); renderEvidence(); }
        Object.entries(state.players).forEach(([kind, player]) => { const matched = state.result[kind].words[index]; if (matched) { player.audio.pause(); player.stopAt = null; seekPlayer(player, matched.start); } });
        if (!finding) { document.querySelectorAll('.word.selected').forEach(node => node.classList.remove('selected')); button.classList.add('selected'); }
      }); return button;
    }));
  }
  function renderSummary() {
    const result = state.result, summary = result?.summary;
    const score = summary?.score;
    $('overall-score').textContent = Number.isFinite(score) ? String(Math.round(score)) : '—';
    $('score-caption').textContent = result ? Number.isFinite(score) ? 'out of 100 · current rubric' : 'Score withheld.' : 'A comparison, not a grade.';
    $('result-label').textContent = result ? summary?.status === 'unreliable' ? 'UNCERTAIN ALIGNMENT' : 'ANALYZED' : 'NO RESULT YET';
    $('summary-caption').textContent = summary?.caption || 'Scores appear only after the audio has been aligned and measured.';
    $('dimension-scores').replaceChildren(...C.dimensions.map(key => {
      const dimension = summary?.dimensions?.find(item => item.key === key); const item = el('div', 'dimension'), heading = el('div', 'dimension-heading'), label = el('span', 'dimension-label');
      label.append(el('i', `legend-dot ${key}-dot`), document.createTextNode(C.labels[key]));
      heading.append(label, el('span', 'dimension-value', Number.isFinite(dimension?.score) ? `${Math.round(dimension.score)} / 100` : '— / 100'));
      const bar = el('div', 'dimension-bar'), fill = el('div', 'dimension-fill'); fill.dataset.type = key; fill.style.width = `${Number.isFinite(dimension?.score) ? C.clamp(dimension.score, 0, 100) : 0}%`; bar.append(fill); bar.setAttribute('aria-hidden', 'true'); item.append(heading, bar); return item;
    }));
    const warnings = result?.warnings || []; $('result-warnings').hidden = !warnings.length; $('result-warnings').replaceChildren(...warnings.map(message => el('p', '', message)));
    $('result-meta').hidden = !result;
    if (result) {
      const info = [`${summary?.flag_count ?? result.findings?.length ?? 0} measured intervals`, `Alignment confidence ${fmt.format((summary?.alignment_confidence || 0) * 100)}%`];
      if (Number.isFinite(summary?.assessed_word_count) && Number.isFinite(summary?.total_word_count)) info.push(`Assessed ${summary.assessed_word_count} of ${summary.total_word_count} words${Number.isFinite(summary.assessed_fraction) ? ` (${Math.round(summary.assessed_fraction * 100)}%)` : ''}`);
      if (result.compute?.seconds !== undefined) info.push(`${fmt.format(result.compute.seconds)}s total · ${deviceLabel(result.compute.device)} alignment${result.compute.cached_alignment ? ' · includes cached alignment' : ''}`);
      if (result.rubric?.version) info.push(`Rubric ${result.rubric.version}`);
      if (result.provenance?.synthetic) info.push('Generated demo variation');
      $('result-meta').replaceChildren(...info.map(text => el('p', '', text)));
    }
  }
  function typeTag(type) { const tag = el('span', 'type-tag'); tag.append(el('i', `legend-dot ${type}-dot`), document.createTextNode(C.labels[type] || type)); return tag; }
  function emptyState(title, text) { const wrap = el('div', 'empty-state'), copy = el('div'); copy.append(el('h3', '', title), el('p', '', text)); wrap.append(el('span', 'empty-crosshair', '⌖'), copy); return wrap; }
  function renderFindings() {
    const findings = state.result?.findings || []; $('findings-count').textContent = `${findings.length} INTERVAL${findings.length === 1 ? '' : 'S'}`;
    if (!findings.length) {
      $('findings-list').replaceChildren(emptyState(state.result ? state.result.summary?.status === 'unreliable' ? 'No reliable intervals to inspect.' : 'No differences crossed this rubric.' : 'Start with the sound.', state.result ? state.result.summary?.status === 'unreliable' ? 'Review the alignment warnings and try a closer transcript or clearer recording.' : 'This comparison did not produce a flagged interval. You can still inspect the audio and aligned words.' : 'Analyze a comparison to see where delivery changes, and why it was flagged.')); return;
    }
    $('findings-list').replaceChildren(...findings.map(finding => {
      const button = el('button', 'finding'); button.type = 'button'; button.dataset.finding = finding.id; button.setAttribute('aria-pressed', 'false');
      const time = el('span', 'finding-time', `${C.time(finding.start, true)}\n${C.time(finding.end, true)}`); time.style.whiteSpace = 'pre-line';
      const title = el('span'); title.append(el('span', 'finding-title', finding.title), el('span', 'finding-sub', `${finding.severity} · participant interval`));
      button.append(time, title, typeTag(finding.type)); button.addEventListener('click', () => selectFinding(finding.id)); return button;
    }));
  }
  function selectFinding(id, seek = true) {
    const finding = state.result?.findings?.find(item => item.id === id); if (!finding) return;
    state.selected = id; updateSelection(); renderEvidence();
    if (seek) Object.entries(state.players).forEach(([kind, player]) => { player.audio.pause(); player.stopAt = null; seekPlayer(player, C.findingInterval(finding, kind, player.recording.duration).start); });
  }
  function updateSelection() {
    const finding = state.result?.findings?.find(item => item.id === state.selected);
    document.querySelectorAll('[data-finding]').forEach(button => { const selected = button.dataset.finding === state.selected; button.classList.toggle('selected', selected); button.setAttribute('aria-pressed', String(selected)); });
    document.querySelectorAll('.word').forEach((button, index) => button.classList.toggle('selected', Boolean(finding?.word_indices?.includes(index))));
    Object.entries(state.players).forEach(([kind, player]) => {
      if (!finding) { player.band.setAttribute('width', '0'); return; }
      const interval = C.findingInterval(finding, kind, player.recording.duration);
      player.band.setAttribute('x', 4 + interval.start / player.recording.duration * 672); player.band.setAttribute('width', Math.max(2, (interval.end - interval.start) / player.recording.duration * 672));
    });
  }
  function renderEvidence() {
    const host = $('evidence-detail'), finding = state.result?.findings?.find(item => item.id === state.selected);
    if (!finding) {
      const empty = el('div', 'inspector-empty'), symbol = el('div', 'evidence-symbol'); symbol.setAttribute('aria-hidden', 'true'); for (let i = 0; i < 5; i++) symbol.append(el('span'));
      empty.append(symbol, el('h3', '', state.result ? 'Explore the recording.' : 'Follow a moment.'), el('p', '', 'Select a flagged interval to hear it and inspect the measurements behind it.')); host.replaceChildren(empty); return;
    }
    const top = el('div', 'evidence-topline'); top.append(typeTag(finding.type), el('span', 'small muted', finding.severity));
    const grid = el('div', 'measurement-grid');
    ['reference', 'participant'].forEach(kind => { const box = el('div', 'measurement'); box.append(el('span', 'measurement-label', kind === 'reference' ? 'REFERENCE' : 'PARTICIPANT'), el('strong', 'measurement-value', Number.isFinite(finding.evidence?.[kind]) ? fmt.format(finding.evidence[kind]) : '—'), el('span', 'measurement-unit', finding.evidence?.unit || '')); grid.append(box); });
    const advice = el('div', 'evidence-advice'); advice.append(el('span', 'advice-label', 'TRY THIS'), document.createTextNode(finding.advice || 'Listen to each interval and decide what supports your intended delivery.'));
    const actions = el('div', 'evidence-play'); ['participant', 'reference'].forEach(kind => {
      const player = state.players[kind]; if (!player) return;
      const interval = C.playbackInterval(finding, kind, player.recording.duration);
      const button = el('button', `button ${kind === 'participant' ? 'primary' : 'outline'}`, `Play ${kind} context`); button.type = 'button';
      button.append(el('span', 'evidence-play-time', `${C.time(interval.start, true)}–${C.time(interval.end, true)}`));
      button.addEventListener('click', () => { seekPlayer(player, interval.start); player.stopAt = interval.end; playAudio(player); }); actions.append(button);
    });
    host.replaceChildren(top, el('h3', 'evidence-detail-title', finding.title), el('p', 'evidence-explanation', finding.explanation), grid, el('p', 'small muted', finding.evidence?.measurement || ''), advice, actions, el('p', 'evidence-confidence', `Interval confidence: ${fmt.format((finding.confidence || 0) * 100)}% · ${C.time(finding.start, true)}–${C.time(finding.end, true)}`));
  }
  async function openMethodology() {
    const dialog = $('methodology-dialog'); if (!dialog.open) dialog.showModal();
    state.methodologyController?.abort(); state.methodologyController = new AbortController();
    try {
      const data = await request('/api/methodology', {}, state.methodologyController.signal);
      const details = el('details'), summary = el('summary', '', `Versioned rubric${data.version ? ` · ${data.version}` : ''}`), pre = el('pre', '', JSON.stringify(data, null, 2)); details.append(summary, pre); $('methodology-server').replaceChildren(details);
    } catch (error) { if (error.name !== 'AbortError') $('methodology-server').replaceChildren(el('p', 'small muted', 'The versioned rubric could not be loaded. Close and reopen this panel to retry.')); }
  }
  function exportReport(printable) {
    if (!state.result?.id) return;
    if (state.hosted) {
      const content = printable ? H.printableReport(state.result) : JSON.stringify(H.exportableResult(state.result), null, 2);
      const url = URL.createObjectURL(new Blob([content], { type: printable ? 'text/html;charset=utf-8' : 'application/json' }));
      const link = el('a'); link.href = url;
      if (printable) { link.target = '_blank'; link.rel = 'noopener'; } else link.download = `speaktrace-${state.result.id}.json`;
      document.body.append(link); link.click(); link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 60000); return;
    }
    const link = el('a'); link.href = `/api/results/${encodeURIComponent(state.result.id)}/report${printable ? '.html' : ''}`;
    if (printable) { link.target = '_blank'; link.rel = 'noopener'; } else link.download = `speaktrace-${state.result.id}.json`;
    document.body.append(link); link.click(); link.remove();
  }
  bindAction('demo-mode', () => setMode('demo'));
  bindAction('upload-mode', () => setMode('upload'));
  bindAction('refresh-library', () => { loadLibrary(); loadHealth(); });
  $('analyze-button').addEventListener('click', startAnalysis);
  $('upload-form').addEventListener('submit', event => { event.preventDefault(); if (!event.isComposing) startAnalysis(); });
  bindAction('stop-watching', () => { state.controller?.abort(); setBusy(false); setNotice(state.hosted ? 'Stopped waiting. Cloud work may still finish, but its result will not be saved. Analyze again when ready.' : 'Stopped watching. The server may continue this job; resume to check its result.', 'info', Boolean(state.jobId)); });
  bindAction('resume-job', resumeJob);
  bindAction('reset-weights', () => { state.weights = { ...C.defaults }; renderWeights(); updateAnalyzeState(); });
  bindAction('edit-comparison', () => {
    const expanded = $('setup-panel').classList.toggle('editing');
    $('edit-comparison').setAttribute('aria-expanded', String(expanded));
    $('edit-comparison').textContent = expanded ? 'Hide inputs' : 'Edit inputs';
  });
  ['reference', 'participant'].forEach(key => {
    $(`${key}-file`).addEventListener('change', event => setFile(key, event.target.files[0] || null));
    bindAction(`${key}-remove`, () => setFile(key, null));
    const drop = $(`${key}-drop`);
    drop.addEventListener('dragover', event => { event.preventDefault(); if (!state.busy) drop.classList.add('dragging'); });
    drop.addEventListener('dragleave', () => drop.classList.remove('dragging'));
    drop.addEventListener('drop', event => { event.preventDefault(); drop.classList.remove('dragging'); if (state.busy) return; if (event.dataTransfer.files.length !== 1) { setFieldError(key, 'Drop one recording into each field.'); return; } setFile(key, event.dataTransfer.files[0]); });
  });
  $('transcript-input').addEventListener('input', event => {
    updateDraftState();
    $('word-count').textContent = `${C.wordCount(event.target.value)} / 150 words`;
    event.target.style.height = 'auto'; event.target.style.height = `${Math.min(300, Math.max(114, event.target.scrollHeight))}px`;
    if (event.target.getAttribute('aria-invalid') === 'true') setFieldError('transcript', C.validateTranscript(event.target.value));
    if (state.result || state.jobId) invalidate(); renderTranscript();
  });
  ['methodology-button', 'privacy-button'].forEach(id => bindAction(id, openMethodology));
  ['close-methodology', 'methodology-done'].forEach(id => bindAction(id, () => $('methodology-dialog').close()));
  $('methodology-dialog').addEventListener('close', () => state.methodologyController?.abort());
  $('download-json').addEventListener('click', () => exportReport(false)); $('print-report').addEventListener('click', () => exportReport(true));
  window.addEventListener('beforeunload', event => { if (state.dirty) { event.preventDefault(); event.returnValue = ''; } });
  window.addEventListener('online', () => loadHealth());
  renderWeights(); clearResult(); updateAnalyzeState(); loadHealth(); loadLibrary();
})();
