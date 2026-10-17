from __future__ import annotations

import asyncio

from app.services.news_service import fetch_news
from app.services.weather_service import get_weather


async def generate_daily_briefing() -> str:
    async def safe_news():
        try:
            return await fetch_news(category="general")
        except RuntimeError:
            return []

    news, weather = await asyncio.gather(safe_news(), get_weather())
    titles = [" ".join(str(article.get("title", "")).split()) for article in news[:5] if article.get("title")]
    if not titles:
        titles = ["No major news headlines are available right now."]
    weather_summary = weather.get("summary") or "Weather unavailable."
    return f"{weather_summary} Top headlines: " + "; ".join(titles)
