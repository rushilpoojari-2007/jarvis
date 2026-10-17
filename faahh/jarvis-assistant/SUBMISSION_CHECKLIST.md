# Submission Checklist

**Checked:** 2026-10-16

- [x] `start.bat` starts the app on `127.0.0.1:8000`; health and missing-key chat behavior passed with placeholder credentials.
- [x] Core chat request, saved history, and response flow pass with a mocked assistant.
- [x] Missing NVIDIA credentials return a clear message in tests.
- [x] One live NVIDIA completion returned HTTP 200 using values already present in the local `.env`; no further live calls were made.
- [x] Runtime and development requirements are pinned and installed in `jarvis-assistant/.venv`.
- [x] `run_test.py`, `run_test.bat`, and `run_test.cmd`: **16 passed** each. `test_chat.py`: **2 passed**.
- [x] VS Code recommendations are present; Python, Pylance, and Python Debugger extensions were verified installed.
- [x] Chat page and health route expose NVIDIA configuration status without returning the key.
- [x] No API key was added to source, documentation, or `.env.example`; `.env` remains excluded by `.gitignore`.
- [x] README, recovery findings, and known limitations are documented.
- [ ] Before manually creating a submission ZIP, exclude `.env`, `.venv`, database files, logs, caches, and uploaded images. The local `.env` contains non-placeholder values.
- [ ] No Git metadata exists, so the tracked-file check cannot be confirmed.
- [ ] News, weather, and image-analysis integrations need separate live checks if required; they were not called during the automated tests.
- [ ] Browser-based interaction and JavaScript syntax were not separately checked because Node.js/browser automation is unavailable here.
- [x] Removed the temporary `.startup-check.db` from the startup smoke check; the active `jarvis.db` was preserved.

## Demonstration

From `jarvis-assistant/`, run `start.bat` or:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000` and select **AI Chat**. The chat page displays whether NVIDIA AI is configured. Do not include the local `.env` in a manual submission archive.
