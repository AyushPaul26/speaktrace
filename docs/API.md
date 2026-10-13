# SpeakTrace API contract v1

All timing values are seconds. Data is JSON except audio uploads and media files. Local and hosted modes use different analysis transports, described below.

## Local endpoints

These endpoints are same-origin on the local server started by `run.py`.

- `GET /api/health`: `{status:"ok", model_ready:bool, device:"cpu"|"cuda", requested_device:"auto"|"cpu"|"cuda", device_name, precision:"float32", torch_version, cuda_version, fallback_reason:string|null, warnings:string[], demo_count:int, version:string}`. Device is the selected runtime backend; a CUDA memory fallback persists on CPU until restart.
- `GET /api/demos`: `{demos:[{id,title,speaker,description,transcript,duration,source_url,license,variants:[{id,label,flaw,severity}]}]}`.
- `POST /api/analyze`: multipart fields `reference` (audio), `participant` (audio), `transcript` (text), optional `weights` (JSON object with pacing/pauses/energy numbers). Returns 202 `{job_id}`.
- `POST /api/demos/{demo_id}/analyze`: JSON `{variant_id, weights?:{pacing:40,pauses:35,energy:25}}`. Returns 202 `{job_id}`. A clean variant compares the original against itself.
- `GET /api/jobs/{job_id}`: `{job_id,status:"queued"|"running"|"complete"|"error",stage:string,progress:number,result?:Analysis,error?:string}`. Poll at about 1 second; progress is staged, not an ETA.
- `GET /api/results/{id}/report`: download full analysis JSON.
- `GET /api/results/{id}/report.html`: self-contained printable HTML report.
- `/media/...`: actual local result or demo audio. The server determines URLs; the client must never construct arbitrary filesystem paths.
- `GET /api/methodology`: versioned rubric/source/limitation metadata.

Errors use JSON `detail` with appropriate 4xx/5xx codes. User uploads need not be preserved on errors. Local result media expires after 24 hours; cleanup runs on startup, new jobs and result access. Demo media persists. This local transport does not send recordings to the cloud.

## Hosted endpoints

The Vercel adapter exposes a synchronous CPU API. Browser POSTs require an `Origin` matching the request host; missing or cross-origin origins are rejected. This check is not user authentication.

- `GET /api/health`: adds `deployment:"vercel"`, `synchronous:true`, `max_seconds:30`, `upload_max_bytes:4200000` and `upload_encoding:"WAV PCM16 mono 16000 Hz"` to the runtime metadata. The frontend uses these fields to select cloud transport and disclose remote processing.
- `GET /api/demos` and `GET /api/methodology`: return the public example library and hosted processing/rubric information.
- `POST /api/hosted/analyze`: multipart `reference`, `participant`, `transcript` and optional JSON `weights`. Both files must be mono 16 kHz PCM16 WAV, **2–30 seconds each**, prepared by the browser from the selected recordings. The full multipart body must not exceed **4,200,000 bytes**. Success returns **200 with the complete Analysis**, rather than a job identifier.
- `POST /api/hosted/demos/{demo_id}/analyze`: JSON `{variant_id, weights?}`. Runs the same uncached pipeline on the selected public audio and returns 200 with the complete Analysis.

Hosted results add `deployment:"vercel"` and `retention`. Uploaded recordings have `url:null` in the server response; the browser attaches its own temporary object URLs to the exact prepared WAVs for playback. Demo recordings use public `/data/...wav` URLs served through the CDN. JSON export removes upload object URLs, and printable reports are generated in the browser. There are no hosted job-polling, saved-report or uploaded-media endpoints; reloading the page discards the current result.

The server permits one analysis at a time per function instance and returns 429 when that instance is busy. Invalid input returns 422, an oversized request returns 413, and unavailable model/runtime resources return 503. This is not a global queue or rate limit. The platform also imposes execution and usage limits; the client must handle timeouts and platform errors.

Hosted audio and transcripts are sent to Vercel. Request-scoped audio files are removed after normal completion or handled errors, but platform termination can interrupt cleanup. The application creates no persistent upload store or alignment cache for hosted requests. See [deployment scope and verification](DEPLOYMENT.md).

## Analysis

```
{
  id, title, created_at, transcript, mode: "demo"|"upload",
  audio_processing: {sample_rate:16000,encoding:"PCM_16",reference_gain,participant_gain,note},
  compute: {device:"cpu"|"cuda"|"cuda+cpu", requested_device, runtime_device, device_name,
    precision:"float32", torch_version, cuda_version, fallback_reason, warnings,
    alignment:"wav2vec2-ctc", seconds, model, revision, cached_alignment:bool,
    feature_device:"cpu", alignment_runs:{reference:DeviceRun,participant:DeviceRun}},
  reference: Recording,
  participant: Recording,
  summary: {
    score: number|null, flag_count: number, alignment_confidence: number,
    status:"complete"|"unreliable", caption: string,
    dimensions:[{key:"pacing"|"pauses"|"energy",label,score:number|null,weight:number}]
  },
  findings:[{
    id,type:"pacing"|"pauses"|"energy",title,start,end,
    reference_start,reference_end,severity:"mild"|"moderate"|"severe",
    severity_value:number,word_indices:number[],explanation,advice,confidence:number,
    evidence:{measurement:string,reference:number,participant:number,unit:string}
  }],
  rubric:{version,weights,thresholds}, warnings:string[],
  provenance?:{source_url,license,synthetic:bool,variant,split}
}
Recording = {
  name,url,duration,words:[{word,start,end,score}],
  alignment:{confidence,coverage,transcript_agreement,recognized_text,cached:bool,compute:DeviceRun},
  features:{times:number[],rms_db:number[],pitch_st:(number|null)[],
    spectral_centroid:number[],mfcc_summary:number[],
    waveform:[{t,min,max}],voiced_fraction:number}
}
DeviceRun = {device:"cpu"|"cuda", requested_device, device_name, precision:"float32",
  torch_version,cuda_version,fallback_reason:string|null,warnings:string[],cached?:bool}
```

Alignment metadata records the backend that generated the emissions, including cached emissions. `cuda+cpu` means the two recordings used different alignment backends (for example after a GPU memory fallback). Acoustic features and comparison run on CPU. Cache keys include model/alignment revision, backend, device name, precision, and Torch/CUDA versions. CPU remains available with `run.py --device cpu`; default `auto` chooses available CUDA, and explicit unavailable CUDA warns then uses CPU. `compute.seconds` measures the whole request, including any cache hits, not a hardware-only inference benchmark.

`features.rms_db` is voiced-median-relative dB, not calibrated sound pressure. `pitch_st` is median-centered semitones; unvoiced values are null. Each recording's time axis is its own actual elapsed time; do not imply a sample-by-sample alignment of different-duration files. Playback changes and word selection stay synchronized. `summary.score=null` means scoring was withheld.

## Python core interfaces

`extract_features(audio: np.ndarray, sample_rate: int) -> dict`: mono float waveform to JSON-safe Recording.features. No model or network calls.

`compare_recordings(reference_audio: np.ndarray, participant_audio: np.ndarray, sample_rate: int, reference_words: list[dict], participant_words: list[dict], transcript: str, weights: dict|None=None) -> dict`: returns `summary`, `findings`, `rubric`, `warnings`; the root orchestrator attaches features/media/metadata. Inputs have the same normalized word sequence, validated by the orchestrator. Coordinates and evidence are always derived from actual words/audio, never generator labels. Reject invalid weights and degenerate input. A low-quality region must be skipped; unreliable recordings withhold scores.

`align_audio(audio: np.ndarray, sample_rate: int, transcript: str) -> dict`: root-owned implementation, returns `{words:[...],confidence,coverage,recognized_text,transcript_agreement,cached,compute}` with actual pretrained CTC alignment. `runtime_metadata() -> dict` returns the current selected backend without loading the model; evaluators should record each alignment's `compute` for actual execution/cache provenance.

## Dataset layout

`data/references/{id}.wav` and `data/references/{id}.json` (id,title,speaker,transcript,source_url,license,source_offset_seconds,split). `data/variants/{reference_id}/{variant_id}.wav`. `data/manifest.json` holds `{version,references:[{...reference fields,audio,variants:[{id,label,flaw,severity,audio,labels:[{type,start,end}],transform}]}]}`. `audio` fields are project-relative paths. The server reads audio/transcript/provenance; `labels`/`transform` are evaluation-only. All descendants of a source recording stay in one split.
