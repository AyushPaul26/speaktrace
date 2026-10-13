"""One-time, free, project-local installation for Python 3.11–3.13."""
from pathlib import Path
import argparse
import os
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def run(arguments):
    print("\n> " + " ".join(map(str, arguments)), flush=True)
    subprocess.run(list(map(str, arguments)), cwd=ROOT, check=True)


def main():
    parser = argparse.ArgumentParser(description="Install SpeakTrace locally (CPU by default).")
    parser.add_argument("--gpu", action="store_true", help="Install optional PyTorch CUDA 12.6 support for an NVIDIA GPU.")
    arguments = parser.parse_args()
    if not (3, 11) <= sys.version_info[:2] < (3, 14):
        raise SystemExit("Install Python 3.12, then run setup again.")
    environment = ROOT / ".venv"
    executable = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not executable.exists():
        run([sys.executable, "-m", "venv", environment])
    pip_check = subprocess.run([str(executable), "-m", "pip", "--version"], capture_output=True)
    if pip_check.returncode:
        run([executable, "-m", "ensurepip", "--upgrade"])
    backend = "cu126" if arguments.gpu else "cpu"
    run([executable, "-m", "pip", "install", "--upgrade", f"torch==2.8.0+{backend}", "--index-url", f"https://download.pytorch.org/whl/{backend}"])
    requirements = ROOT / ("requirements-lock.txt" if os.name == "nt" else "requirements.txt")
    run([executable, "-m", "pip", "install", "-r", requirements])
    run([executable, "scripts/download_model.py"])
    run([executable, "-c", "import torch; print('PyTorch:', torch.__version__); print('GPU:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'Unavailable; CPU will be used')"])
    print("\nSpeakTrace is ready. Run start.bat or use .venv's Python to run run.py.")


if __name__ == "__main__":
    main()
