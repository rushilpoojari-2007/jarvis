from __future__ import annotations

import copy
import logging
import time
from typing import Any

import httpx

from app.config import settings

_WEATHER_CACHE_TTL_SECONDS = 600
_weather_cache: dict[str, tuple[float, dict[str, Any]]] = {}
logger = logging.getLogger("jarvis.weather")


async def _get_weather_uncached(city: str | None = None) -> dict[str, Any]:
    location = (city or settings.DEFAULT_CITY).strip()
    if not location:
        return {"city": "Unknown", "country": "Unknown", "summary": "No city provided for weather lookup."}

    try:
        async with httpx.AsyncClient(timeout=settings.API_TIMEOUT_SECONDS) as client:
            geo = await client.get(
                "https://geocoding-api.open-meteo.com/v1/search",
                params={"name": location, "count": 1, "language": "en", "format": "json"},
            )
            geo.raise_for_status()
            geo_data = geo.json()
            results = geo_data.get("results") or []
            if not results:
                return {"city": location, "country": "Unknown", "summary": f"No weather data found for {location}."}

            place = results[0]
            lat = place["latitude"]
            lon = place["longitude"]
            weather = await client.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "current": "temperature_2m,relative_humidity_2m,weather_code",
                    "timezone": "auto",
                },
            )
            weather.raise_for_status()
            payload = weather.json()
            current = payload.get("current") or {}
            code = current.get("weather_code")
            weather_map = {
                0: "Clear sky",
                1: "Mainly clear",
                2: "Partly cloudy",
                3: "Overcast",
                45: "Fog",
                48: "Rime fog",
                51: "Light drizzle",
                53: "Moderate drizzle",
                55: "Heavy drizzle",
                61: "Slight rain",
                63: "Moderate rain",
                65: "Heavy rain",
                80: "Rain showers",
                81: "Heavy showers",
                82: "Violent showers",
                95: "Thunderstorm",
            }
            summary = weather_map.get(code, "Variable conditions")
            temp = current.get("temperature_2m")
            return {
                "city": place.get("name", location),
                "country": place.get("country", "Unknown"),
                "temperature_c": temp,
                "humidity": current.get("relative_humidity_2m"),
                "weather": summary,
                "summary": f"{summary} in {place.get('name', location)}. Temperature: {temp}°C.",
            }
    except httpx.HTTPStatusError as exc:
        return {
            "city": location,
            "country": "Unknown",
            "summary": f"Weather provider returned HTTP {exc.response.status_code}.",
        }
    except httpx.RequestError:
        return {"city": location, "country": "Unknown", "summary": "Weather lookup failed: network error."}
    except Exception as exc:
        logger.warning("Weather lookup failed (%s)", type(exc).__name__)
        return {"city": location, "country": "Unknown", "summary": "Weather data is temporarily unavailable."}


async def get_weather(city: str | None = None) -> dict[str, Any]:
    location = (city or settings.DEFAULT_CITY).strip()
    if not location:
        return await _get_weather_uncached(city)
    key = location.casefold()
    now = time.monotonic()
    cached = _weather_cache.get(key)
    if cached and now - cached[0] < _WEATHER_CACHE_TTL_SECONDS:
        return copy.deepcopy(cached[1])
    if cached:
        _weather_cache.pop(key, None)

    result = await _get_weather_uncached(city)
    if not result.get("summary", "").startswith("Weather lookup failed:"):
        _weather_cache[key] = (time.monotonic(), result)
        if len(_weather_cache) > 128:
            _weather_cache.pop(next(iter(_weather_cache)))
    return copy.deepcopy(result)
