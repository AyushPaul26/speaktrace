"""Vercel ASGI entry point. The model is provisioned by the build, never a request."""
import os
from pathlib import Path
import tempfile

os.environ.setdefault("SPEAKTRACE_DEVICE", "cpu")
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
os.environ.setdefault("HF_HOME", str(Path(tempfile.gettempdir()) / "speaktrace-huggingface"))
os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "speaktrace-matplotlib"))

from speaktrace import alignment

if os.environ.get("SPEAKTRACE_MODEL_DIR"):
    alignment.MODEL_DIR = Path(os.environ["SPEAKTRACE_MODEL_DIR"])

from api.hosted import create_app

app = create_app()
