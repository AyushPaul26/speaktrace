# SpeakTrace API contract v1

All endpoints are same-origin on the local server. All timing values are seconds. Data is JSON except audio uploads and media files.

- `GET /api/health`: `{status:"ok", model_ready:bool, device:"cpu"|"cuda", requested_device:"auto"|"cpu"|"cuda", device_name, precision:"float32", torch_version, cuda_version, fallback_reason:string|null, warnings:string[], demo_count:int, version:string}`. Device is the selected runtime backend; a CUDA memory fallback persists on CPU until restart.
- `GET /api/demos`: `{demos:[{id,title,speaker,description,transcript,duration,source_url,license,variants:[{id,label,flaw,severity}]}]}`.
- `POST /api/analyze`: multipart fields `reference` (audio), `participant` (audio), `transcript` (text), optional `weights` (JSON object with pacing/pauses/energy numbers). Returns 202 `{job_id}`.
- `POST /api/demos/{demo_id}/analyze`: JSON `{variant_id, weights?:{pacing:40,pauses:35,energy:25}}`. Returns 202 `{job_id}`. A clean variant compares the original against itself.
- `GET /api/jobs/{job_id}`: `{job_id,status:"queued"|"running"|"complete"|"error",stage:string,progress:number,result?:Analysis,error?:string}`. Poll at about 1 second; progress is staged, not an ETA.
- `GET /api/results/{id}/report`: download full analysis JSON.
- `GET /api/results/{id}/report.html`: self-contained printable HTML report.
- `/media/...`: actual local result or demo audio. The server determines URLs; the client must never construct arbitrary filesystem paths.
- `GET /api/methodology`: versioned rubric/source/limitation metadata.

Errors are JSON `{detail:"actionable message"}` with appropriate 4xx/5xx codes. User uploads need not be preserved on errors. Local result media is retained for at most 24 hours; cleanup runs on startup and job creation. Demo media persists. There is no cloud upload.

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
