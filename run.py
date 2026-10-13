"""Start the local studio; no files leave this laptop."""
from pathlib import Path
import argparse
import os
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description="SpeakTrace local speech studio")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto",
                        help="Alignment device; auto uses the GPU when CUDA is available.")
    arguments = parser.parse_args()
    if not 1024 <= arguments.port <= 65535:
        parser.error("Use a port between 1024 and 65535.")
    os.environ["SPEAKTRACE_DEVICE"] = arguments.device
    try:
        import uvicorn
    except ImportError:
        raise SystemExit("Dependencies are missing. Run setup.bat first.")
    url = f"http://127.0.0.1:{arguments.port}"
    from speaktrace.alignment import runtime_metadata
    compute = runtime_metadata()
    print(f"\nSpeakTrace | {compute['device_name']} | {compute['precision']} | Local audio\nOpen {url}\nPress Ctrl+C to stop.\n", flush=True)
    for warning in compute["warnings"]:
        print(warning, flush=True)
    uvicorn.run("speaktrace.api:app", host="127.0.0.1", port=arguments.port, log_level="info")


if __name__ == "__main__":
    main()
