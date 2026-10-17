@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo Python virtual environment not found. See README.md for setup instructions.
  exit /b 1
)

".venv\Scripts\python.exe" -c "import fastapi, uvicorn" >nul 2>nul
if errorlevel 1 (
  echo Installing application dependencies into .venv...
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
  if errorlevel 1 exit /b 1
)

if not exist ".env" (
  copy ".env.example" ".env" >nul
  if errorlevel 1 exit /b 1
  echo Created .env from .env.example. Add your NVIDIA_API_KEY to enable AI chat.
)

".venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000
