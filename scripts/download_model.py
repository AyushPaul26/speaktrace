"""Download one free CPU-compatible model locally; subsequent inference is offline."""
from __future__ import annotations
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PINNED_REVISION = "22aad52d435eb6dbaf354bdad9b0da84ce7d6156"
os.environ["HF_HOME"] = str(ROOT / ".cache" / "huggingface")
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
os.environ["HF_HUB_DISABLE_XET"] = "1"


def main():
    from huggingface_hub import HfApi, snapshot_download

    model = "facebook/wav2vec2-base-960h"
    destination = ROOT / ".models" / "wav2vec2-base-960h"
    metadata_file = destination / "speaktrace-model.json"
    if metadata_file.exists() and (destination / "config.json").exists() and any(
        (destination / name).exists() for name in ("model.safetensors", "pytorch_model.bin")
    ):
        print("Speech model already installed locally.")
        return
    info = HfApi().model_info(model, revision=PINNED_REVISION)
    names = {item.rfilename for item in info.siblings}
    weight = "model.safetensors" if "model.safetensors" in names else "pytorch_model.bin"
    patterns = [weight, "config.json", "preprocessor_config.json", "tokenizer_config.json", "vocab.json", "special_tokens_map.json", "README.md"]
    print(f"Downloading {model} at immutable revision {info.sha}. CPU only; no account required.", flush=True)
    snapshot_download(model, revision=info.sha, local_dir=destination, allow_patterns=patterns, max_workers=2)
    metadata_file.write_text(json.dumps({"model": model, "revision": info.sha,
        "license": "apache-2.0", "source": f"https://huggingface.co/{model}", "weights": weight}, indent=2), encoding="utf-8")
    print("Model is ready. User recordings will be processed locally.")


if __name__ == "__main__":
    main()
