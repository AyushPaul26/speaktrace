"""Bounded, synchronous cloud transport around the unchanged analysis pipeline.

There are no persistent jobs, media endpoints, uploads, or alignment caches here.
Model files must be packaged at build time; request handlers never download them.
"""
from __future__ import annotations

import io
import json
import logging
from pathlib import Path
import tempfile
import threading
from urllib.parse import urlsplit
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
import numpy as np
from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, ValidationError, field_validator
import soundfile as sf
from starlette.concurrency import run_in_threadpool

from speaktrace import __version__
from speaktrace.alignment import PROJECT_ROOT, model_ready, normalize_transcript, runtime_metadata
from speaktrace.audio import decode_audio
from speaktrace.core.comparison import rubric_metadata
from speaktrace.pipeline import run_analysis

MAX_REQUEST_BYTES = 4_200_000
MAX_SECONDS = 30
MAX_AUDIO_BYTES = MAX_SECONDS * 16000 * 2 + 128
_analysis_slot = threading.BoundedSemaphore(1)


def _prepare_runtime():
    """Apply the hosted CPU budget after the common loader sets its defaults."""
    import torch
    from speaktrace.alignment import _load_model

    _load_model()
    torch.set_num_threads(1)


class HostedBoundary:
    """Buffer only bounded bodies; reject cross-origin requests before parsing."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = {key.decode("latin-1").lower(): value.decode("latin-1") for key, value in scope["headers"]}
        if scope["method"] in ("POST", "PUT", "PATCH", "DELETE"):
            origin = urlsplit(headers.get("origin", ""))
            if origin.scheme not in ("http", "https") or origin.netloc != headers.get("host") or headers.get("sec-fetch-site") == "cross-site":
                return await JSONResponse({"detail": "Open SpeakTrace on this website to submit a comparison."}, status_code=403)(scope, receive, send)
            try:
                size = int(headers.get("content-length", "0"))
                if size < 0:
                    raise ValueError
            except ValueError:
                return await JSONResponse({"detail": "Invalid request size."}, status_code=400)(scope, receive, send)
            if size > MAX_REQUEST_BYTES:
                return await JSONResponse({"detail": "The hosted request must fit within 4.2 MB. Use two recordings of at most 30 seconds."}, status_code=413)(scope, receive, send)
            body = bytearray()
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    return
                body.extend(message.get("body", b""))
                if len(body) > MAX_REQUEST_BYTES:
                    return await JSONResponse({"detail": "The hosted request exceeds 4.2 MB."}, status_code=413)(scope, receive, send)
                if not message.get("more_body", False):
                    break
            delivered = False
            original_receive = receive
            async def replay():
                nonlocal delivered
                if not delivered:
                    delivered = True
                    return {"type": "http.request", "body": bytes(body), "more_body": False}
                return await original_receive()
            receive = replay
        async def secure_send(message):
            if message["type"] == "http.response.start":
                message.setdefault("headers", []).extend([
                    (b"cache-control", b"no-store"),
                    (b"x-content-type-options", b"nosniff"),
                    (b"referrer-policy", b"no-referrer"),
                ])
            await send(message)
        return await self.app(scope, receive, secure_send)


class Weights(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pacing: FiniteFloat = Field(default=40, ge=0, le=100)
    pauses: FiniteFloat = Field(default=35, ge=0, le=100)
    energy: FiniteFloat = Field(default=25, ge=0, le=100)

    @field_validator("pacing", "pauses", "energy", mode="before")
    @classmethod
    def require_number(cls, value):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("Weights must be numbers.")
        return value


class DemoRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    variant_id: str = Field(min_length=1, max_length=100)
    weights: Weights = Field(default_factory=Weights)


def _weights(value: dict) -> dict:
    weights = Weights.model_validate(value).model_dump()
    if sum(weights.values()) <= 0:
        raise ValueError("Give at least one rubric dimension a weight greater than zero.")
    return weights


def _canonical_upload(content: bytes) -> np.ndarray:
    """Accept browser-produced PCM whose samples remain identical in playback."""
    if len(content) > MAX_AUDIO_BYTES:
        raise ValueError("Each hosted recording must be at most 30 seconds long. The local app supports up to 60 seconds.")
    try:
        with sf.SoundFile(io.BytesIO(content)) as sound:
            if (sound.format != "WAV" or sound.subtype != "PCM_16" or sound.channels != 1 or sound.samplerate != 16000):
                raise ValueError("The hosted upload must be mono 16 kHz PCM16 WAV. Let the website prepare your recordings.")
            if not 2 <= len(sound) / sound.samplerate <= MAX_SECONDS:
                raise ValueError("Each hosted recording must be between 2 and 30 seconds long. The local app supports up to 60 seconds.")
    except (RuntimeError, sf.LibsndfileError) as error:
        raise ValueError("The converted audio could not be read. Select your recording again.") from error
    audio, _ = decode_audio(content)
    if float(np.max(np.abs(audio))) < .01:
        raise ValueError("The converted audio is too quiet. Let the website normalize the recording before upload.")
    return audio


def create_app(project_root: Path = PROJECT_ROOT) -> FastAPI:
    root = Path(project_root)
    app = FastAPI(title="SpeakTrace hosted", version=__version__, docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(HostedBoundary)

    def references():
        manifest = root / "data" / "manifest.json"
        return json.loads(manifest.read_text(encoding="utf-8")).get("references", []) if manifest.is_file() else []

    def audio_file(relative: str) -> Path:
        path = (root / relative).resolve()
        if not path.is_relative_to((root / "data").resolve()) or not path.is_file():
            raise HTTPException(404, "This demo audio is unavailable.")
        return path

    def execute(*, playback_urls=None, **arguments):
        if any(len(arguments[role + "_audio"]) > MAX_SECONDS * 16000 for role in ("reference", "participant")):
            raise HTTPException(422, "Each hosted recording must be at most 30 seconds long. The local app supports up to 60 seconds.")
        if not model_ready():
            raise HTTPException(503, "The hosted speech model is unavailable. Please retry later or use the local app.")
        if not _analysis_slot.acquire(blocking=False):
            raise HTTPException(429, "This server is analyzing another comparison. Please retry in a moment.")
        try:
            _prepare_runtime()
            with tempfile.TemporaryDirectory(prefix="speaktrace-request-") as temporary:
                # Passing upload mode explicitly disables alignment disk caches even
                # for demos. Result mode and public playback paths are restored below.
                result = run_analysis(uuid4().hex, Path(temporary), lambda *_: None, mode="upload", **arguments)
            result["mode"] = "demo" if playback_urls else "upload"
            result["deployment"] = "vercel"
            result["retention"] = "Uploaded audio is processed on this server and request files are removed when analysis finishes. Results remain in your browser; no persistent report or audio URL is created."
            for role in ("reference", "participant"):
                result[role]["url"] = playback_urls[role] if playback_urls else None
            return result
        except ValueError as error:
            raise HTTPException(422, str(error)) from error
        except (RuntimeError, MemoryError) as error:
            logging.getLogger(__name__).error("Hosted analysis failed: %s", type(error).__name__)
            raise HTTPException(503, "The server could not complete this analysis. Try shorter recordings or run SpeakTrace locally.") from error
        finally:
            _analysis_slot.release()

    @app.get("/")
    def studio():
        return FileResponse(root / "web" / "index.html", media_type="text/html")

    @app.get("/api/health")
    def health():
        return {"status": "ok", "model_ready": model_ready(), **runtime_metadata(), "version": __version__,
                "demo_count": len(references()), "deployment": "vercel", "synchronous": True,
                "upload_max_bytes": MAX_REQUEST_BYTES, "upload_encoding": "WAV PCM16 mono 16000 Hz", "max_seconds": MAX_SECONDS}

    @app.get("/api/demos")
    def demos():
        return {"demos": [{"id": r["id"], "title": r["title"], "speaker": r["speaker"],
            "description": r.get("description", "Public-domain reference with generated delivery changes."),
            "transcript": r["transcript"], "duration": r.get("duration", 0), "source_url": r["source_url"], "license": r["license"],
            "variants": [{k: v.get(k) for k in ("id", "label", "flaw", "severity")} for v in r["variants"]]} for r in references()]}

    @app.get("/api/methodology")
    def methodology():
        return {"rubric": rubric_metadata(), "model": "facebook/wav2vec2-base-960h", **runtime_metadata(),
            "scope": "English, one speaker, same supplied transcript; 2–30 seconds per hosted recording; at most 150 words. The local app supports up to 60 seconds.",
            "retention": "Audio is sent to this server for analysis. Request files are removed when analysis finishes. No persistent jobs or audio/report URLs are stored; your current result remains in the browser.",
            "limitations": ["Reference differences are not universal delivery flaws.", "CTC alignment quality is a heuristic, not a calibrated probability.",
                "Microphone movement can change relative energy.", "Synthetic benchmark performance is not independent human validation.",
                "Pitch, MFCC and spectrum are diagnostics, not stand-alone quality scores.",
                "The free hosted service has bounded request size, memory and execution time. Shorter clips are more reliable."],
            "sources": [{"title": r["title"], "speaker": r["speaker"], "url": r["source_url"], "license": r["license"]} for r in references()]}

    @app.post("/api/hosted/analyze")
    async def analyze_upload(reference: UploadFile = File(...), participant: UploadFile = File(...),
                             transcript: str = Form(...), weights: str = Form("{}")):
        try:
            normalize_transcript(transcript)
            parsed_weights = _weights(json.loads(weights))
            recordings = [_canonical_upload(await upload.read(MAX_AUDIO_BYTES + 1)) for upload in (reference, participant)]
        except (ValueError, ValidationError) as error:
            raise HTTPException(422, str(error)) from error
        finally:
            await reference.close()
            await participant.close()
        return await run_in_threadpool(execute, reference_audio=recordings[0], participant_audio=recordings[1],
            transcript=transcript, reference_name=Path(reference.filename or "Reference").name[:120],
            participant_name=Path(participant.filename or "Participant").name[:120], weights=parsed_weights)

    @app.post("/api/hosted/demos/{demo_id}/analyze")
    def analyze_demo(demo_id: str, payload: DemoRequest):
        try:
            weights = _weights(payload.weights.model_dump())
        except ValueError as error:
            raise HTTPException(422, str(error)) from error
        reference = next((r for r in references() if r["id"] == demo_id), None)
        if reference is None:
            raise HTTPException(404, "This demo was not found.")
        variant = next((v for v in reference["variants"] if v["id"] == payload.variant_id), None)
        if variant is None:
            raise HTTPException(404, "This example was not found.")
        try:
            ref_audio, _ = decode_audio(audio_file(reference["audio"]))
            participant_audio, _ = decode_audio(audio_file(variant["audio"]))
        except ValueError as error:
            raise HTTPException(422, str(error)) from error
        return execute(reference_audio=ref_audio, participant_audio=participant_audio, transcript=reference["transcript"],
            reference_name=reference["speaker"] + " · Reference", participant_name=variant["label"],
            title=reference["title"], weights=weights,
            playback_urls={"reference": "/" + reference["audio"], "participant": "/" + variant["audio"]},
            provenance={"source_url": reference["source_url"], "license": reference["license"],
                "synthetic": variant.get("flaw") not in ("clean", None), "variant": variant["label"], "split": reference.get("split")})

    return app
