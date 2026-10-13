"""Prepare the pinned model in Vercel's remote build environment."""
from pathlib import Path
import os
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def build():
    # The model is downloaded during the remote build, never on visitor requests.
    # The developer's installed environment, private recordings and caches are excluded.
    if os.environ.get("VERCEL") != "1":
        raise SystemExit("Run this build on Vercel; it intentionally avoids another local model download.")
    os.environ.pop("HF_HUB_OFFLINE", None)
    os.environ.pop("TRANSFORMERS_OFFLINE", None)
    sys.path.insert(0, str(ROOT / "scripts"))
    from download_model import main as download_model
    download_model()
    # Measure the actual Linux CPU wheel on the remote builder before publishing.
    subprocess.run([sys.executable, str(ROOT / "scripts/probe_hosted_memory.py")], check=True)

    # StaticFiles mounts expose only source web assets and the public WAV folders.
    # Vercel promotes them to its CDN; the API retains a working static fallback.
    model_bytes = sum(p.stat().st_size for p in (ROOT / ".models").rglob("*") if p.is_file())
    print(f"Pinned acoustic model ready: {model_bytes:,} bytes. No user recordings included.")


if __name__ == "__main__":
    build()
