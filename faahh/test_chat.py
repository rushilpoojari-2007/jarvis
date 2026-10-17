from pathlib import Path
import subprocess
import sys


WORKSPACE = Path(__file__).resolve().parent
PROJECT = WORKSPACE / "jarvis-assistant"
PYTHON = PROJECT / ".venv" / "Scripts" / "python.exe"

if not PYTHON.is_file():
    print(f"Project virtual environment not found: {PYTHON}", file=sys.stderr)
    print("See jarvis-assistant/README.md for setup instructions.", file=sys.stderr)
    raise SystemExit(2)

raise SystemExit(subprocess.call([str(PYTHON), "test_chat.py"], cwd=PROJECT))
