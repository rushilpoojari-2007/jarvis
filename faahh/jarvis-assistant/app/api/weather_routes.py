import logging

from fastapi import APIRouter, HTTPException, Query

from app.services.weather_service import get_weather

router = APIRouter(prefix="/api/weather", tags=["weather"])
logger = logging.getLogger("jarvis.weather")


@router.get("/")
async def get_current_weather(city: str | None = Query(default=None)):
    try:
        return await get_weather(city)
    except Exception as exc:
        logger.warning("Weather route failed (%s)", type(exc).__name__)
        raise HTTPException(status_code=502, detail="Weather provider could not complete the request.") from None
