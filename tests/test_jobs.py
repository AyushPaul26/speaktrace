import json
from pathlib import Path
import time
import os

from speaktrace.jobs import JobManager


def test_failed_job_preserves_actionable_error_and_has_no_result(tmp_path):
    manager = JobManager(tmp_path)
    def fail(job_id, directory, progress):
        progress("Checking audio", 20)
        raise ValueError("The transcript does not match the recording.")
    job_id = manager.submit(fail)
    for _ in range(100):
        status = manager.get(job_id)
        if status["status"] == "error":
            break
        time.sleep(0.01)
    manager.close()
    assert status["status"] == "error"
    assert "transcript" in status["error"]
    assert "result" not in status


def test_completed_result_is_persisted_and_reloadable(tmp_path):
    manager = JobManager(tmp_path)
    job_id = manager.submit(lambda identifier, directory, progress: {"id": identifier, "summary": {"score": 92}})
    manager.close()
    assert manager.get(job_id)["result"]["summary"]["score"] == 92
    second = JobManager(tmp_path)
    assert second.get(job_id)["status"] == "complete"
    second.close()


def test_restart_marks_interrupted_job_failed(tmp_path):
    identifier = "a" * 32
    directory = tmp_path / ".runtime" / "jobs" / identifier
    directory.mkdir(parents=True)
    (directory / "job.json").write_text(json.dumps({"job_id": identifier, "status": "running", "stage": "Working", "progress": 20}), encoding="utf-8")
    manager = JobManager(tmp_path)
    assert manager.get(identifier)["status"] == "error"
    assert "restart" in manager.get(identifier)["error"].lower()
    manager.close()


def test_expired_result_is_unavailable_without_another_submission(tmp_path):
    manager = JobManager(tmp_path)
    identifier = manager.submit(lambda job_id, directory, progress: {"id": job_id})
    manager.close()
    directory = manager.directory / identifier
    old = time.time() - 25 * 3600
    os.utime(directory, (old, old))
    assert manager.get(identifier) is None
    assert not directory.exists()
