# JARVIS Personal AI Assistant

JARVIS is a local web app for AI chat, tasks, bookmarks, news, weather, and daily briefings. FastAPI serves the API and the responsive HTML/CSS/JavaScript interface. Conversation and task data are stored in SQLite.

## Features

- NVIDIA chat completions with configurable model, endpoint, timeouts, and fallback model.
- Session conversations with persistent history.
- Chat tools for tasks, bookmarks, news, weather, and briefings.
- Image attachments for AI image review.
- Current news through configured providers, with Google News RSS as a keyless fallback.
- Weather from Open-Meteo and scheduled briefings.
- Local API and database health diagnostics.
- Graceful startup and shutdown of the scheduled job.

## Requirements

- Windows 10 or 11.
- Python 3.11 or later. Python 3.13 is supported by the dependency set.
- Network access for live NVIDIA, news, and weather integrations.

## Setup

Open PowerShell in this directory (`jarvis-assistant`) and create the virtual environment:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

If the copied virtual environment is broken and the `uv` command is available, recreate it with the local managed Python:

```powershell
uv venv --clear --python 3.13 .venv
uv pip install --python .venv\Scripts\python.exe -r requirements.txt
```

To run the tests as well, install the development dependencies:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

Create a local environment file only if one does not already exist. Keep existing credentials intact:

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

Edit `.env` locally and set `NVIDIA_API_KEY` to enable AI chat. Chat image review uses `NVIDIA_VISION_API_KEY` when set, otherwise it reuses `NVIDIA_API_KEY`. Optional news provider keys are `NEWS_API_KEY`, `GNEWS_API_KEY`, and `GUARDIAN_API_KEY`; news also has a keyless RSS fallback. Never put keys in source code or share the `.env` file.

## Run

Start the app with:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Or double-click `start.bat`. Open [http://127.0.0.1:8000](http://127.0.0.1:8000), and open `/chat` for chat. API documentation is at `/docs`; health diagnostics are at `/health`.

The server binds to loopback only. Stop it with Ctrl+C. The scheduler stops with the server process.

## Tests

Run all tests without using the local `.env` credentials or production database:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests
```

For the mocked chat flow only, run `test_chat.py` or:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_chat.py
```

The test suite uses an in-memory SQLite database and mocked provider responses. It does not call NVIDIA or external news/weather services.

## Configuration

See `.env.example` for supported variables. Important settings:

| Variable | Purpose | Default |
| --- | --- | --- |
| `NVIDIA_API_KEY` | NVIDIA hosted chat credential | unset |
| `NVIDIA_VISION_API_KEY` | Optional NVIDIA vision credential for image attachments in chat | falls back to `NVIDIA_API_KEY` |
| `NVIDIA_BASE_URL` | NVIDIA API base URL | `https://integrate.api.nvidia.com/v1` |
| `NVIDIA_MODEL` | Primary chat model | `openai/gpt-oss-20b` |
| `NVIDIA_FALLBACK_MODEL` | Fallback model | `nvidia/nemotron-3.5-lightning-30b-a3b` |
| `API_TIMEOUT_SECONDS` | News/weather request timeout | `15.0` |
| `NVIDIA_TIMEOUT_SECONDS` | Model request timeout | `12.0` |
| `DEFAULT_CITY` | Default weather location | `Belagavi` |
| `DATABASE_URL` | SQLAlchemy connection URL | `sqlite:///./jarvis.db` |
| `APP_TIMEZONE` | Display/scheduler timezone setting | `Asia/Kolkata` in example |

The chat page shows whether NVIDIA chat and image review are configured. `/health` reports database, scheduler, chat, and image review configuration without making credentialed provider calls.

## Known limitations

- Live model access, model availability, and account limits require a valid NVIDIA credential and were not verified by the offline tests.
- News and weather need an internet connection. Provider rate limits and regional availability can affect live results.
- Scheduled briefings run only while the local app is running; this is a single-process personal app, not a hosted service.
- Browser speech recognition and speech synthesis depend on browser support and may use browser-provided services.
- The project has no Git metadata, so original commit history and untracked-file status cannot be recovered here.
- The workspace's existing local `.env` contains non-placeholder values. It was preserved and is excluded by `.gitignore`; omit it from any manual ZIP or submission copy.
- One live NVIDIA chat completion was observed during startup verification because those existing values loaded; subsequent startup checks and all automated tests used placeholder credentials or mocks.

## Troubleshooting

- If the virtual environment came from another Windows account or machine, recreate it with the setup command above.
- If a module is missing, run `.\.venv\Scripts\python.exe -m pip install -r requirements.txt` from this directory.
- If AI chat says the NVIDIA key is missing, check `NVIDIA_API_KEY` in `.env` and restart the server.
- If the app port is already in use, stop the other local process or change the port in the Uvicorn command and `start.bat`.
