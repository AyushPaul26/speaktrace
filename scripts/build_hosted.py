"""Prepare public assets and the pinned model in Vercel's remote build environment."""
from pathlib import Path
import json
import os
import shutil
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

    public = ROOT / "public"
    public.mkdir(exist_ok=True)
    shutil.copyfile(ROOT / "web/index.html", public / "index.html")
    shutil.copytree(ROOT / "web", public / "web", dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("*.test.cjs", "*.py", "__pycache__"))
    manifest = json.loads((ROOT / "data/manifest.json").read_text(encoding="utf-8"))
    for reference in manifest["references"]:
        for recording in [reference, *reference["variants"]]:
            source = (ROOT / recording["audio"]).resolve()
            if not source.is_relative_to(ROOT / "data") or source.suffix != ".wav":
                raise ValueError("Unexpected public demo audio path")
            target = public / recording["audio"]
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
    model_bytes = sum(p.stat().st_size for p in (ROOT / ".models").rglob("*") if p.is_file())
    print(f"Hosted assets ready; pinned acoustic model: {model_bytes:,} bytes. No user recordings included.")


if __name__ == "__main__":
    build()
