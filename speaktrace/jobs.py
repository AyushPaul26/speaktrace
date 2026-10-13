"""Bounded serial analysis jobs with restart-aware, local-only result retention."""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shutil
import threading
import time
import uuid


class JobManager:
    def __init__(self, project_root: Path):
        self.directory = project_root / ".runtime" / "jobs"
        self.directory.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._jobs: dict[str, dict] = {}
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="speaktrace-analysis")
        self.cleanup()
        for state_file in self.directory.glob("*/job.json"):
            try:
                state = json.loads(state_file.read_text(encoding="utf-8"))
                identifier = state["job_id"]
                if not re.fullmatch(r"[a-f0-9]{32}", identifier):
                    continue
                if state["status"] in ("queued", "running"):
                    state.update(status="error", error="The server restarted before this analysis finished. Run the comparison again.", stage="Interrupted")
                self._jobs[identifier] = state
            except (ValueError, KeyError, OSError):
                continue

    def cleanup(self):
        """Remove only expired, resolved direct children of this app's jobs folder."""
        root = self.directory.resolve()
        with self._lock:
            for child in self.directory.iterdir():
                if (not child.is_dir() or child.is_symlink() or child.resolve().parent != root
                        or not re.fullmatch(r"[a-f0-9]{32}", child.name)):
                    continue
                if self._jobs.get(child.name, {}).get("status") in ("running", "queued"):
                    continue
                if time.time() - child.stat().st_mtime > 24 * 3600:
                    shutil.rmtree(child)
                    self._jobs.pop(child.name, None)

    def _save(self, identifier):
        path = self.directory / identifier / "job.json"
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self._jobs[identifier], ensure_ascii=False, allow_nan=False), encoding="utf-8")
        temporary.replace(path)

    def submit(self, work) -> str:
        self.cleanup()
        with self._lock:
            if sum(j["status"] in ("queued", "running") for j in self._jobs.values()) >= 4:
                raise ValueError("Four analyses are already queued. Wait for one to finish and try again.")
            identifier = uuid.uuid4().hex
            directory = self.directory / identifier
            directory.mkdir()
            self._jobs[identifier] = {"job_id": identifier, "status": "queued", "stage": "Waiting for the analysis worker", "progress": 0,
                                      "created_at": datetime.now(timezone.utc).isoformat()}
            self._save(identifier)
            self._executor.submit(self._run, identifier, directory, work)
            return identifier

    def _run(self, identifier, directory, work):
        def progress(stage, percent):
            with self._lock:
                self._jobs[identifier].update(status="running", stage=stage, progress=int(percent))
                self._save(identifier)
        try:
            progress("Preparing comparison", 5)
            result = work(identifier, directory, progress)
            (directory / "result.json").write_text(json.dumps(result, ensure_ascii=False, allow_nan=False), encoding="utf-8")
            with self._lock:
                self._jobs[identifier].update(status="complete", stage="Analysis ready", progress=100)
                self._save(identifier)
        except Exception as error:
            # Avoid exposing filesystem paths/tracebacks through the browser.
            message = str(error) if isinstance(error, (ValueError, RuntimeError)) else "Analysis could not finish. Check the recording format and restart the app if the problem continues."
            with self._lock:
                self._jobs[identifier].update(status="error", stage="Analysis stopped", error=message)
                self._save(identifier)
            for audio in directory.glob("*.wav"):
                audio.unlink(missing_ok=True)

    def get(self, identifier: str) -> dict | None:
        self.cleanup()
        with self._lock:
            state = self._jobs.get(identifier)
            if not state:
                return None
            result = dict(state)
            if state["status"] == "complete":
                path = self.directory / identifier / "result.json"
                if path.is_file():
                    result["result"] = json.loads(path.read_text(encoding="utf-8"))
            return result

    def close(self):
        self._executor.shutdown(wait=True)
