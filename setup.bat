@echo off
setlocal
cd /d "%~dp0"
py -3.12 scripts\setup.py
if errorlevel 1 (
  echo Setup stopped. Read the error above. Python 3.12 and an internet connection are needed for initial setup.
  pause
  exit /b 1
)
echo Setup complete. Double-click start.bat to open the local studio.
pause
