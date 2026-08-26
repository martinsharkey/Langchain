@echo off
REM Standalone launcher for the trading bot (VPS / outside VS Code) — see DEPLOY.md.
REM Starts dashboard (:5000) + engine + research + CryptoRTI feed via app.py.
cd /d "%~dp0"
if not exist "venv\Scripts\python.exe" (
  echo [run_bot] venv not found - create it: python -m venv venv ^&^& venv\Scripts\pip install -r requirements.txt
  exit /b 1
)
set MODE=%1
if "%MODE%"=="" set MODE=LIVE_MICRO
echo [run_bot] starting app.py %MODE% ...
"venv\Scripts\python.exe" app.py %MODE%
