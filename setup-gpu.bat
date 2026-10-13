@echo off
setlocal
cd /d "%~dp0"
py -3.12 scripts\setup.py --gpu
if errorlevel 1 (
  echo GPU setup stopped. Read the error above. Python 3.12 and an internet connection are needed for initial setup.
  pause
  exit /b 1
)
echo Setup complete. Double-click start.bat to use automatic GPU detection.
pause
