@echo off
cd /d "%~dp0"
if not exist "jarvis-assistant\.venv\Scripts\python.exe" (
  echo Project virtual environment not found. See jarvis-assistant\README.md.
  exit /b 2
)
"jarvis-assistant\.venv\Scripts\python.exe" run_test.py
exit /b %errorlevel%
