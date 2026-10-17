@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Virtual environment not found. See README.md for setup instructions.
  exit /b 1
)
".venv\Scripts\python.exe" -m pytest -q tests
exit /b %errorlevel%
