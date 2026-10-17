import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import SQLAlchemyError
from starlette.responses import FileResponse

import app.models  # noqa: F401
from app.api.bookmarks_routes import router as bookmarks_router
from app.api.briefing_routes import router as briefing_router
from app.api.chat_routes import router as chat_router
from app.api.news_routes import router as news_router
from app.api.settings_routes import router as settings_router
from app.api.tasks_routes import router as tasks_router
from app.api.weather_routes import router as weather_router
from app.config import settings
from app.database import engine, init_db
from app.scheduler import is_scheduler_running, start_scheduler, stop_scheduler

logging.basicConfig(level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO))
logger = logging.getLogger("jarvis")
BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    start_scheduler()
    logger.info("JARVIS application started")
    try:
        yield
    finally:
        stop_scheduler()
        logger.info("JARVIS application shutdown complete")


app = FastAPI(
    title="JARVIS Personal AI Life Assistant",
    version=settings.APP_VERSION,
    description="Local AI dashboard for personal productivity, weather, news, and briefings.",
    lifespan=lifespan,
)

app.include_router(tasks_router)
app.include_router(news_router)
app.include_router(weather_router)
app.include_router(briefing_router)
app.include_router(chat_router)
app.include_router(bookmarks_router)
app.include_router(settings_router)


@app.get("/health")
async def health_check() -> dict:
    try:
        with engine.connect() as connection:
            connection.exec_driver_sql("SELECT 1")
        database_status = "ready"
    except SQLAlchemyError as exc:
        logger.warning("Health check database probe failed (%s)", type(exc).__name__)
        database_status = "unavailable"

    return {
        "status": "ok" if database_status == "ready" else "degraded",
        "app": "JARVIS",
        "version": settings.APP_VERSION,
        "database": database_status,
        "scheduler": "running" if is_scheduler_running() else "stopped",
        "integrations": {
            "nvidia_ai": {"configured": settings.ai_enabled(), "live_check": "not_performed"},
            "nvidia_vision": {
                "configured": bool(settings.NVIDIA_VISION_API_KEY),
                "live_check": "not_performed",
            },
            "news": {"configured": settings.news_enabled(), "live_check": "not_performed"},
        },
    }


@app.get("/")
async def serve_frontend() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/news", include_in_schema=False)
async def serve_news_page() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "news.html")


@app.get("/briefing", include_in_schema=False)
async def serve_briefing_page() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "briefing.html")


@app.get("/tasks", include_in_schema=False)
async def serve_tasks_page() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "tasks.html")


@app.get("/weather", include_in_schema=False)
async def serve_weather_page() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "weather.html")


@app.get("/chat", include_in_schema=False)
async def serve_chat_page() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "chat.html")


app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")
