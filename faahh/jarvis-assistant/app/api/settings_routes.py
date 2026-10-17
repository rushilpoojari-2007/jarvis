from fastapi import APIRouter

from app.config import settings

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("/")
async def get_settings():
    return {
        "app_name": settings.APP_NAME,
        "timezone": settings.APP_TIMEZONE,
        "default_city": settings.DEFAULT_CITY,
        "news_enabled": settings.news_enabled(),
        "ai_enabled": settings.ai_enabled(),
        "image_analysis_enabled": bool(settings.NVIDIA_VISION_API_KEY),
        "ai_provider": "NVIDIA" if settings.ai_enabled() else None,
        "ai_status": "configured" if settings.ai_enabled() else "missing_api_key",
    }
