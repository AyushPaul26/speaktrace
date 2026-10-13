@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Run setup-gpu.bat once before starting SpeakTrace.
  pause
  exit /b 1
)
echo Open http://127.0.0.1:8765 in your browser after the server starts.
".venv\Scripts\python.exe" run.py --device cuda
if errorlevel 1 pause
