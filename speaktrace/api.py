"""Same-origin local web API. Launch bound to 127.0.0.1, never a public interface."""
from __future__ import annotations
from contextlib import asynccontextmanager
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, ValidationError
from starlette.middleware.trustedhost import TrustedHostMiddleware

from . import __version__
from .alignment import model_ready, normalize_transcript, PROJECT_ROOT, runtime_metadata
from .audio import decode_audio, MAX_BYTES
from .jobs import JobManager
from .pipeline import run_analysis
from .reports import html_report

MAX_REQUEST_BYTES = 2 * MAX_BYTES + 65536


class BodyLimitMiddleware:
    """Enforce the body limit even when a sender omits Content-Length."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        received = 0
        async def bounded_receive():
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > MAX_REQUEST_BYTES:
                    raise HTTPException(413, "Each audio file must be no larger than 20 MB.")
            return message
        await self.app(scope, bounded_receive if scope["type"] == "http" else receive, send)


class Weights(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pacing: FiniteFloat = Field(default=40, ge=0, le=100)
    pauses: FiniteFloat = Field(default=35, ge=0, le=100)
    energy: FiniteFloat = Field(default=25, ge=0, le=100)


class DemoRequest(BaseModel):
    variant_id: str = Field(min_length=1, max_length=100)
    weights: Weights = Field(default_factory=Weights)


def _weights(value: dict) -> dict:
    weights = Weights.model_validate(value).model_dump()
    if sum(weights.values()) <= 0:
        raise ValueError("Give at least one rubric dimension a weight greater than zero.")
    return weights


def create_app(project_root: Path = PROJECT_ROOT) -> FastAPI:
    root = Path(project_root)
    manager = JobManager(root)

    @asynccontextmanager
    async def lifespan(app):
        yield
        manager.close()

    app = FastAPI(title="SpeakTrace", version=__version__, lifespan=lifespan, docs_url=None, redoc_url=None)
    app.state.jobs = manager
    app.add_middleware(BodyLimitMiddleware)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"])

    @app.middleware("http")
    async def local_request_guard(request: Request, call_next):
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            origin = request.headers.get("origin")
            if origin and (urlsplit(origin).netloc != request.headers.get("host") or urlsplit(origin).scheme not in ("http", "https")):
                return JSONResponse({"detail": "Open SpeakTrace in its own local browser tab to submit audio."}, status_code=403)
            try:
                size = int(request.headers.get("content-length", "0"))
            except ValueError:
                return JSONResponse({"detail": "Invalid request size."}, status_code=400)
            if size > MAX_REQUEST_BYTES:
                return JSONResponse({"detail": "Each audio file must be no larger than 20 MB."}, status_code=413)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; media-src 'self' blob:; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'"
        if request.url.path.startswith(("/api/", "/media/jobs/")):
            response.headers["Cache-Control"] = "no-store"
        return response

    def references():
        path = root / "data" / "manifest.json"
        if not path.exists():
            return []
        return json.loads(path.read_text(encoding="utf-8")).get("references", [])

    def data_audio(relative: str) -> Path:
        path = (root / relative).resolve()
        if not path.is_relative_to((root / "data").resolve()) or not path.is_file():
            raise HTTPException(404, "Demo audio is missing. Run the dataset setup and try again.")
        return path

    def enqueue(**arguments):
        if not model_ready():
            raise HTTPException(503, "Install the free speech model with setup.bat, then try again.")
        try:
            identifier = manager.submit(lambda job_id, directory, progress: run_analysis(job_id, directory, progress, **arguments))
        except ValueError as error:
            raise HTTPException(429, str(error)) from error
        return JSONResponse({"job_id": identifier}, status_code=202)

    @app.get("/api/health")
    def health():
        return {"status": "ok", "model_ready": model_ready(), **runtime_metadata(), "demo_count": len(references()), "version": __version__}

    @app.get("/api/demos")
    def demos():
        return {"demos": [{"id": r["id"], "title": r["title"], "speaker": r["speaker"],
            "description": r.get("description", "Public-domain reference with controlled delivery variants."),
            "transcript": r["transcript"], "duration": r.get("duration", 0),
            "source_url": r["source_url"], "license": r["license"],
            "variants": [{k: v.get(k) for k in ("id", "label", "flaw", "severity")} for v in r["variants"]]}
            for r in references()]}

    @app.post("/api/demos/{demo_id}/analyze")
    def analyze_demo(demo_id: str, payload: DemoRequest):
        try:
            weights = _weights(payload.weights.model_dump())
        except ValueError as error:
            raise HTTPException(422, str(error)) from error
        reference = next((r for r in references() if r["id"] == demo_id), None)
        if reference is None:
            raise HTTPException(404, "This demo was not found. Refresh the demo library.")
        variant = next((v for v in reference["variants"] if v["id"] == payload.variant_id), None)
        if variant is None:
            raise HTTPException(404, "This example was not found. Choose another variant.")
        try:
            ref_audio, _ = decode_audio(data_audio(reference["audio"]))
            participant, _ = decode_audio(data_audio(variant["audio"]))
        except ValueError as error:
            raise HTTPException(422, str(error)) from error
        return enqueue(reference_audio=ref_audio, participant_audio=participant, transcript=reference["transcript"],
            reference_name=reference["speaker"] + " · Reference", participant_name=variant["label"],
            title=reference["title"], mode="demo", weights=weights,
            provenance={"source_url": reference["source_url"], "license": reference["license"],
                "synthetic": variant.get("flaw") not in ("clean", None), "variant": variant["label"], "split": reference.get("split")})

    @app.post("/api/analyze")
    async def analyze_upload(reference: UploadFile = File(...), participant: UploadFile = File(...),
                             transcript: str = Form(...), weights: str = Form("{}")):
        try:
            normalize_transcript(transcript)
            parsed_weights = _weights(json.loads(weights))
            files = []
            for upload in (reference, participant):
                content = await upload.read(MAX_BYTES + 1)
                files.append(decode_audio(content)[0])
        except (ValueError, ValidationError) as error:
            raise HTTPException(422, str(error)) from error
        finally:
            await reference.close()
            await participant.close()
        return enqueue(reference_audio=files[0], participant_audio=files[1], transcript=transcript,
            reference_name=(Path(reference.filename or "Reference").name[:120]),
            participant_name=(Path(participant.filename or "Participant").name[:120]), weights=parsed_weights)

    @app.get("/api/jobs/{job_id}")
    def job(job_id: str):
        state = manager.get(job_id)
        if state is None:
            raise HTTPException(404, "This analysis is unavailable or has expired. Run it again.")
        return state

    @app.get("/api/results/{job_id}/report")
    def report(job_id: str):
        state = manager.get(job_id)
        if not state or state["status"] != "complete":
            raise HTTPException(404, "The report is not ready or has expired.")
        return JSONResponse(state["result"], headers={"Content-Disposition": f'attachment; filename="speaktrace-{job_id[:8]}.json"'})

    @app.get("/api/results/{job_id}/report.html", response_class=HTMLResponse)
    def printable_report(job_id: str):
        state = manager.get(job_id)
        if not state or state["status"] != "complete":
            raise HTTPException(404, "The report is not ready or has expired.")
        return html_report(state["result"])

    @app.get("/api/methodology")
    def methodology():
        from .core.comparison import rubric_metadata
        return {"rubric": rubric_metadata(), "model": "facebook/wav2vec2-base-960h", **runtime_metadata(),
            "scope": "English, one speaker, same supplied transcript; 2–60 seconds per recording.",
            "retention": "Audio and reports stay in this project's local runtime folder. Expired results are cleaned after 24 hours on startup or the next analysis.",
            "limitations": ["Reference differences are not universal delivery flaws.", "CTC alignment quality is a heuristic, not a calibrated probability.",
                "Microphone movement can change relative energy.", "Synthetic benchmark performance is not independent human validation.",
                "Pitch, MFCC and spectrum are diagnostics, not stand-alone quality scores."],
            "sources": [{"title": r["title"], "speaker": r["speaker"], "url": r["source_url"], "license": r["license"]} for r in references()]}

    @app.get("/media/jobs/{job_id}/{filename}")
    def media(job_id: str, filename: str):
        if not re.fullmatch(r"[a-f0-9]{32}", job_id) or filename not in ("reference.wav", "participant.wav"):
            raise HTTPException(404, "Audio not found.")
        if manager.get(job_id) is None:
            raise HTTPException(404, "Audio unavailable or expired.")
        path = manager.directory / job_id / filename
        if not path.is_file():
            raise HTTPException(404, "Audio unavailable or expired.")
        return FileResponse(path, media_type="audio/wav")

    if (root / "web").exists():
        app.mount("/web", StaticFiles(directory=root / "web"), name="assets")
        app.mount("/", StaticFiles(directory=root / "web", html=True), name="web")
    return app


app = create_app()
